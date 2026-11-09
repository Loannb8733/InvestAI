import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.errors import TooManyRequestsError, UnauthorizedError
from app.core.redis_client import _get_redis_txt

logger = logging.getLogger(__name__)

LOCKOUT_THRESHOLD = 10
LOCKOUT_WINDOW_S = 900
TOTP_REPLAY_WINDOW_S = 90
ACCESS_REVOCATION_CAP_S = 3600
REFRESH_REVOCATION_CAP_S = 7 * 86400

_fallback: dict[str, tuple[int, float]] = {}


def _fallback_get(key: str) -> int:
    value, expires_at = _fallback.get(key, (0, 0.0))
    return value if expires_at > time.monotonic() else 0


def _fallback_set(key: str, value: int, ttl_s: int) -> None:
    now = time.monotonic()
    for stale in [k for k, (_, expires_at) in _fallback.items() if expires_at <= now]:
        del _fallback[stale]
    _fallback[key] = (value, now + ttl_s)


def _fail_key(user_id: UUID) -> str:
    return f"login_fail:{user_id}"


def _totp_key(user_id: UUID, code: str) -> str:
    return f"totp_used:{user_id}:{code}"


async def ensure_not_locked(user_id: UUID) -> None:
    """Refuse un compte verrouillé ; Redis injoignable, le compteur de secours de ce processus fait foi."""
    key = _fail_key(user_id)
    try:
        failures = int(await (await _get_redis_txt()).get(key) or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login lockout store unavailable, using this process's counter: %s", exc)
        failures = _fallback_get(key)
    if failures >= LOCKOUT_THRESHOLD:
        raise TooManyRequestsError("Compte temporairement verrouillé. Veuillez réessayer dans 15 minutes.")


async def record_failure(user_id: UUID) -> None:
    """Compte un échec de connexion, dans Redis ou à défaut dans le compteur de secours."""
    key = _fail_key(user_id)
    try:
        redis = await _get_redis_txt()
        await redis.incr(key)
        await redis.expire(key, LOCKOUT_WINDOW_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login failure counted in this process only (Redis unreachable) for user %s: %s", user_id, exc)
        _fallback_set(key, _fallback_get(key) + 1, LOCKOUT_WINDOW_S)


async def clear_failures(user_id: UUID) -> None:
    key = _fail_key(user_id)
    _fallback.pop(key, None)
    try:
        await (await _get_redis_txt()).delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to clear login failure counter for user %s: %s", user_id, exc)


async def ensure_totp_unused(user_id: UUID, code: str) -> None:
    """Refuse un code TOTP déjà servi ; Redis injoignable, le registre de secours de ce processus fait foi."""
    key = _totp_key(user_id, code)
    try:
        used = bool(await (await _get_redis_txt()).exists(key))
    except Exception as exc:  # noqa: BLE001
        logger.warning("MFA anti-replay store unavailable, using this process's registry: %s", exc)
        used = _fallback_get(key) > 0
    if used:
        raise UnauthorizedError("MFA code already used. Wait for the next code.")


async def mark_totp_used(user_id: UUID, code: str) -> None:
    key = _totp_key(user_id, code)
    try:
        await (await _get_redis_txt()).set(key, "1", ex=TOTP_REPLAY_WINDOW_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TOTP code marked used in this process only (Redis unreachable) for user %s: %s", user_id, exc)
        _fallback_set(key, 1, TOTP_REPLAY_WINDOW_S)


async def is_revoked(jti: str) -> bool:
    """Le jeton a-t-il été révoqué ? Ouvert par défaut si Redis est injoignable, contournement journalisé en ERROR."""
    try:
        return bool(await (await _get_redis_txt()).exists(f"token_blocklist:{jti}"))
    except Exception as exc:  # noqa: BLE001
        logger.error("SECURITY: token revocation check bypassed (Redis unreachable, failing open): %s", exc)
        return False


async def revoke(payload: dict[str, Any], cap_s: int) -> None:
    """Révoque un jeton pour le reste de sa durée de vie, plafonnée à ``cap_s``."""
    jti = payload.get("jti")
    if not jti:
        return
    ttl = min(max(1, int(payload.get("exp", 0) - datetime.now(UTC).timestamp())), cap_s)
    try:
        await (await _get_redis_txt()).set(f"token_blocklist:{jti}", "1", ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.error("SECURITY: %s token not revoked on logout (Redis unreachable): %s", payload.get("type"), exc)
