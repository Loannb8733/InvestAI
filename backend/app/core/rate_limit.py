"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from starlette.requests import Request

from app.core.config import settings
from app.core.redis_client import redis_async_url, redis_ssl_kwargs


def _get_real_client_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For (behind Nginx/proxy)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in the chain is the original client
        return forwarded.split(",")[0].strip()
    forwarded = request.headers.get("X-Real-IP")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "127.0.0.1"


def _limiter_storage_uri() -> str:
    """Return a cleaned Redis URL for the synchronous limits storage.

    Reuses the same cleaning logic as the async client to strip
    ssl_cert_reqs=CERT_NONE which redis-py 5.x rejects as a string.
    """
    return redis_async_url()


def _limiter_storage_options() -> dict:
    """Return SSL kwargs for the synchronous limits Redis connection."""
    return redis_ssl_kwargs()


# Create limiter instance.
#
# Resilience trade-off (single-instance Render free tier):
# - storage = Upstash Redis when reachable (shared counter, correct under scale).
# - swallow_errors=True + in_memory_fallback_enabled=True: if Upstash blips,
#   slowapi falls back to a per-process counter rather than disabling limits.
#   On the current single-web-instance topology this is still effective.
#
# ⚠ When scaling horizontally (paid tier, multiple instances), set
# ``in_memory_fallback_enabled=False`` AND ``swallow_errors=False`` so a Redis
# outage fails closed instead of degrading to per-instance counters that an
# attacker can bypass by striping requests across replicas.
limiter = Limiter(
    key_func=_get_real_client_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri=_limiter_storage_uri(),
    storage_options=_limiter_storage_options(),
    strategy="fixed-window",
    swallow_errors=True,
    in_memory_fallback_enabled=True,
)

# Specific rate limits for different endpoint types
RATE_LIMITS = {
    # Authentication - stricter limits to prevent brute force
    "auth_login": "5/minute",
    "auth_register": "3/minute",
    "auth_refresh": "30/minute",
    # Standard API endpoints
    "api_read": "120/minute",
    "api_write": "60/minute",
    # Heavy operations
    "csv_import": "10/minute",
    "report_generate": "5/minute",
    # Price/external API calls (to respect external rate limits)
    "price_fetch": "30/minute",
}
