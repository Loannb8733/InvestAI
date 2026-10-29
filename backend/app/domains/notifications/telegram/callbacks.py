import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.service import analytics_service
from app.domains.notifications.telegram.client import get_redis, telegram_service
from app.domains.predictions.planned_orders import add_telegram_order
from app.services.smart_insights_service import smart_insights_service

logger = logging.getLogger(__name__)

SIMULATION_TTL = 30
SIMULATION_HORIZON_DAYS = 90
SIMULATION_RUNS = 2000
RUIN_DELTA_POINTS = 1


@dataclass(frozen=True)
class Callback:
    """Appui sur un bouton d'un signal alpha : ``<action>:alpha:<utilisateur>:<symbole>:<montant>``."""

    callback_id: str
    chat_id: str
    message_id: int | None
    action: str
    user_id: str
    symbol: str
    order_eur: float


def _signal_header(symbol: str, order_eur: float) -> str:
    return f"⚠️ <b>InvestAI</b>\n\n🚀 <b>Signal Alpha : {symbol}</b>\nOrdre suggéré: <b>{order_eur:,.2f} €</b>"


def _verdict(ruin_delta: float) -> tuple[str, str]:
    if ruin_delta < -RUIN_DELTA_POINTS:
        return "SÉCURISÉ", "✅"
    if ruin_delta > RUIN_DELTA_POINTS:
        return "RISQUÉ", "⚠️"
    return "NEUTRE", "\U0001f7f0"


async def _simulation_text(db: AsyncSession, callback: Callback) -> str:
    vol_regime = await smart_insights_service.get_current_vol_regime(db, callback.user_id)
    before = await analytics_service.monte_carlo(
        db,
        callback.user_id,
        horizon_days=SIMULATION_HORIZON_DAYS,
        num_simulations=SIMULATION_RUNS,
        vol_regime=vol_regime,
    )
    after = await analytics_service.monte_carlo(
        db,
        callback.user_id,
        horizon_days=SIMULATION_HORIZON_DAYS,
        num_simulations=SIMULATION_RUNS,
        contribution={callback.symbol: callback.order_eur} if callback.order_eur > 0 else None,
        vol_regime=vol_regime,
    )
    verdict, emoji = _verdict(after.prob_ruin - before.prob_ruin)
    return (
        f"{_signal_header(callback.symbol, callback.order_eur)}"
        f"\n\n📊 <b>Simulation Monte Carlo</b>\n"
        f"Ruine: <b>{before.prob_ruin:.1f}%</b> ➡️ <b>{after.prob_ruin:.1f}%</b>\n"
        f"Rendement: {before.expected_return:.1f}% ➡️ {after.expected_return:.1f}%\n"
        f"P(positif): {before.prob_positive:.1f}% ➡️ {after.prob_positive:.1f}%\n\n"
        f"{emoji} Verdict: <b>{verdict}</b>"
    )


async def simulate_ruin(db: AsyncSession, callback: Callback) -> None:
    """Probabilité de ruine à 90 jours avant et après l'ordre ; une simulation par utilisateur toutes les 30 s."""
    redis = await get_redis()
    rate_key = f"tg:mc_rate:{callback.user_id}"
    if await redis.exists(rate_key):
        await telegram_service.answer_callback_query(
            callback.callback_id, "Simulation en cours, patientez 30s...", show_alert=True
        )
        return
    await redis.set(rate_key, "1", ex=SIMULATION_TTL)
    await telegram_service.answer_callback_query(callback.callback_id, "Simulation Monte Carlo en cours...")
    try:
        text = await _simulation_text(db, callback)
        plan_button = {
            "text": "✅ Marquer comme Planifié",
            "callback_data": f"plan_order:alpha:{callback.user_id}:{callback.symbol}:{callback.order_eur}",
        }
        await telegram_service.edit_message(
            callback.chat_id, callback.message_id, text, reply_markup={"inline_keyboard": [[plan_button]]}
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Monte Carlo callback failed for %s/%s: %s", callback.user_id, callback.symbol, exc)
        await telegram_service.send_message(f"Erreur lors de la simulation: {exc}", chat_id=callback.chat_id)


async def plan_order(db: AsyncSession, callback: Callback) -> None:
    """Enregistre l'ordre suggéré comme planifié et retire les boutons du message."""
    await telegram_service.answer_callback_query(callback.callback_id, "Ordre planifié !")
    try:
        await add_telegram_order(db, callback.user_id, callback.symbol, callback.order_eur, callback.chat_id)
        await db.commit()
        text = (
            f"{_signal_header(callback.symbol, callback.order_eur)}\n\n"
            "✅ <b>Ordre planifié !</b>\nVisible dans votre Matrice de Stratégie."
        )
        await telegram_service.edit_message(
            callback.chat_id, callback.message_id, text, reply_markup={"inline_keyboard": []}
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Plan order callback failed for %s/%s: %s", callback.user_id, callback.symbol, exc)
        await telegram_service.send_message(f"Erreur lors de la planification: {exc}", chat_id=callback.chat_id)
