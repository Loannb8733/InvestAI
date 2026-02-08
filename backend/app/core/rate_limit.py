"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri=settings.REDIS_URL,
    strategy="fixed-window",
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
