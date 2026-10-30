import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.exchanges.models import APIKey

logger = logging.getLogger(__name__)

AUTH_MARKERS = ("invalid key", "invalid signature", "permission denied")
THROTTLED = {
    418: "L'exchange bloque temporairement l'adresse IP du serveur (HTTP 418)",
    429: "Quota de l'exchange atteint (HTTP 429)",
}


def describe(exc: Exception) -> str:
    """Erreur lisible ; une erreur HTTP se résume à son statut, sans l'URL signée."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return THROTTLED.get(status, f"HTTP {status} {exc.response.reason_phrase}")
    return str(exc)


def mark_failure(key: APIKey, exc: Exception) -> None:
    """Identifiants refusés (HTTP ou corps Kraken) : clé désactivée ; 418 et 429 : quota ; sinon erreur."""
    message = describe(exc)
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    if status in (401, 403) or any(marker in message.lower() for marker in AUTH_MARKERS):
        key.mark_auth_failure(message)
        logger.warning("Clé API %s refusée par l'exchange : désactivée", key.id)
    elif status in THROTTLED:
        key.mark_rate_limited(message)
        logger.warning("Clé API %s : %s", key.id, message)
    else:
        key.mark_error(message)
        logger.error(
            "Clé API %s : erreur de synchronisation : %s",
            key.id,
            message[:200],
            exc_info=exc if status is None else None,
        )


async def rollback_and_mark(session: AsyncSession, key_id: UUID, exc: Exception) -> None:
    """Annule tout le travail en cours, puis n'enregistre que l'échec sur la clé rechargée."""
    await session.rollback()
    key = await session.get(APIKey, key_id)
    if key is None:
        logger.warning("Clé API %s introuvable après rollback : échec non enregistré", key_id)
        return
    mark_failure(key, exc)
    await session.commit()
