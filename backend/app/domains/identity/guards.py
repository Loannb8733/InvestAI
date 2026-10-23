import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.errors import ServiceUnavailableError, TooManyRequestsError, UnauthorizedError
from app.core.redis_client import _get_redis_txt

logger = logging.getLogger(__name__)

LOCKOUT_THRESHOLD = 10
LOCKOUT_WINDOW_S = 900
TOTP_REPLAY_WINDOW_S = 90
ACCESS_REVOCATION_CAP_S = 3600
REFRESH_REVOCATION_CAP_S = 7 * 86400


def _fail_key(user_id: UUID) -> str:
    return f"login_fail:{user_id}"


async def ensure_not_locked(user_id: UUID) -> None:
    """Refuse un compte verrouillé ; refuse aussi si le compteur est injoignable (fermé par défaut)."""
    try:
        failures = int(await (await _get_redis_txt()).get(_fail_key(user_id)) or 0)
    except Exception as exc:
        logger.warning("Login lockout store unavailable: %s", exc)
        raise ServiceUnavailableError(
            "Authentification temporairement indisponible. Réessayez dans un instant."
        ) from exc
    if failures >= LOCKOUT_THRESHOLD:
        raise TooManyRequestsError("Compte temporairement verrouillé. Veuillez réessayer dans 15 minutes.")


async def record_failure(user_id: UUID) -> None:
    try:
        redis = await _get_redis_txt()
        await redis.incr(_fail_key(user_id))
        await redis.expire(_fail_key(user_id), LOCKOUT_WINDOW_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record login failure counter for user %s: %s", user_id, exc)


async def clear_failures(user_id: UUID) -> None:
    try:
        await (await _get_redis_txt()).delete(_fail_key(user_id))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to clear login failure counter for user %s: %s", user_id, exc)


async def ensure_totp_unused(user_id: UUID, code: str) -> None:
    """Refuse un code TOTP déjà servi ; refuse aussi si le registre est injoignable (fermé par défaut)."""
    try:
        used = await (await _get_redis_txt()).exists(f"totp_used:{user_id}:{code}")
    except Exception as exc:
        logger.warning("MFA anti-replay store unavailable: %s", exc)
        raise ServiceUnavailableError("MFA temporarily unavailable. Please retry shortly.") from exc
    if used:
        raise UnauthorizedError("MFA code already used. Wait for the next code.")


async def mark_totp_used(user_id: UUID, code: str) -> None:
    try:
        await (await _get_redis_txt()).set(f"totp_used:{user_id}:{code}", "1", ex=TOTP_REPLAY_WINDOW_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to mark TOTP code used (anti-replay) for user %s: %s", user_id, exc)


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
