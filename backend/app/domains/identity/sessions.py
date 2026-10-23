import logging
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.errors import UnauthorizedError
from app.domains.identity import guards
from app.domains.identity.models import User
from app.domains.identity.repository import UserRepository
from app.domains.identity.tokens import TokenType, decode_token, fingerprint, is_stale

logger = logging.getLogger(__name__)

STALE_SESSION = "Session expirée : le mot de passe a été modifié."
BINDING_FAILED = "Token binding validation failed"
INVALID_MESSAGES: dict[TokenType, str] = {
    "access": "Token invalide ou expiré",
    "refresh": "Token de rafraîchissement invalide",
}


def _check_binding(payload: dict[str, Any], kind: TokenType, user_agent: str) -> None:
    token_fp = payload.get("fp")
    if not token_fp:
        if kind == "access" and settings.is_production:
            logger.warning("Access token missing fingerprint in production (sub=%s)", payload.get("sub"))
            raise UnauthorizedError("Token binding required")
        return
    if token_fp != fingerprint(user_agent):
        logger.warning("Token fingerprint mismatch for user %s", payload.get("sub"))
        raise UnauthorizedError(BINDING_FAILED)


async def authenticate(
    token: str, kind: TokenType, user_agent: str, users: UserRepository
) -> tuple[User, dict[str, Any]]:
    """Utilisateur actif porteur d'un jeton valide de type ``kind``, avec les revendications du jeton."""
    payload = decode_token(token)
    if payload is None:
        raise UnauthorizedError(INVALID_MESSAGES[kind])
    if payload.get("type") != kind:
        raise UnauthorizedError("Type de token invalide" if kind == "access" else INVALID_MESSAGES[kind])
    _check_binding(payload, kind, user_agent)
    jti = payload.get("jti")
    if jti and await guards.is_revoked(jti):
        raise UnauthorizedError("Token has been revoked")
    try:
        user_id = UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise UnauthorizedError("Payload du token invalide") from exc
    user = await users.by_id(user_id)
    if user is None:
        raise UnauthorizedError("Utilisateur non trouvé")
    if not user.is_active:
        raise UnauthorizedError("User is inactive")
    if is_stale(payload, user.token_version):
        logger.info("Jeton d'une génération périmée (sub=%s)", user_id)
        raise UnauthorizedError(STALE_SESSION)
    return user, payload
