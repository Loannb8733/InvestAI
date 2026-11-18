import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.notifications.telegram.client import telegram_service

logger = logging.getLogger(__name__)

RETIRED_NOTICE = (
    "Cette fonction a été retirée : InvestAI ne propose plus d'ordre ni de montant. "
    "Simulez vos propres montants depuis l'application."
)


@dataclass(frozen=True)
class Callback:
    """Appui sur un bouton d'un ancien signal alpha : ``<action>:alpha:<utilisateur>:<symbole>:<montant>``."""

    callback_id: str
    chat_id: str
    message_id: int | None
    action: str
    user_id: str
    symbol: str
    order_eur: float


async def _retired(callback: Callback) -> None:
    """Les boutons « simuler l'ordre suggéré » et « planifier l'ordre suggéré » des anciens messages ne font plus
    rien : ils répondent par une notice, sans simulation ni ordre enregistré."""
    logger.info("Retired Telegram button %s pressed by %s on %s", callback.action, callback.user_id, callback.symbol)
    await telegram_service.answer_callback_query(callback.callback_id, RETIRED_NOTICE, show_alert=True)


async def simulate_ruin(db: AsyncSession, callback: Callback) -> None:
    """Ancien bouton de simulation de l'ordre suggéré : retiré."""
    await _retired(callback)


async def plan_order(db: AsyncSession, callback: Callback) -> None:
    """Ancien bouton de planification de l'ordre suggéré : retiré, aucun ordre n'est créé."""
    await _retired(callback)
