import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.exchanges.models import APIKey

logger = logging.getLogger(__name__)

AUTH_MARKERS = ("invalid key", "invalid signature", "permission denied")


def mark_failure(key: APIKey, exc: Exception) -> None:
    """Identifiants refusés (HTTP ou corps Kraken) : clé désactivée ; 429 : quota ; sinon erreur."""
    message = str(exc)
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    if status in (401, 403) or any(marker in message.lower() for marker in AUTH_MARKERS):
        key.mark_auth_failure(message)
        logger.warning("Clé API %s refusée par l'exchange : désactivée", key.id)
    elif status == 429:
        key.mark_rate_limited(message)
        logger.warning("Clé API %s : quota atteint", key.id)
    else:
        key.mark_error(message)
        logger.error("Clé API %s : erreur de synchronisation : %s", key.id, message[:200])


async def rollback_and_mark(session: AsyncSession, key_id: UUID, exc: Exception) -> None:
    """Annule tout le travail en cours, puis n'enregistre que l'échec sur la clé rechargée."""
    await session.rollback()
    key = await session.get(APIKey, key_id)
    if key is None:
        logger.warning("Clé API %s introuvable après rollback : échec non enregistré", key_id)
        return
    mark_failure(key, exc)
    await session.commit()
