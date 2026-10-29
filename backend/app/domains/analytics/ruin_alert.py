import logging

from app.domains.notifications.telegram.client import telegram_service

logger = logging.getLogger(__name__)


def _ruin_message(prob_ruin: float, horizon_days: int, withdrawal_rate: float, ter: float, monthly_wd: float) -> str:
    params_parts = []
    if monthly_wd > 0:
        params_parts.append(f"retrait {monthly_wd:.0f}€/mois")
    elif withdrawal_rate > 0:
        params_parts.append(f"retrait {withdrawal_rate:.1f}%/an")
    if ter > 0:
        params_parts.append(f"TER {ter:.2f}%")
    params_str = " + ".join(params_parts) if params_parts else "sans retraits"
    return (
        f"📉 <b>Alerte Probabilité de Ruine</b>\n\n"
        f"Votre simulation Monte Carlo ({horizon_days}j, {params_str}) "
        f"indique une probabilité de ruine de <b>{prob_ruin:.1f}%</b>.\n\n"
        f"💡 Envisagez de réduire votre taux de retrait ou de diversifier votre portefeuille."
    )


async def send_ruin_alert(
    chat_id: str,
    user_id: str,
    prob_ruin: float,
    horizon_days: int,
    withdrawal_rate: float,
    ter: float,
    monthly_wd: float = 0.0,
) -> None:
    """Alerte Telegram critique sur une probabilité de ruine élevée ; un échec d'envoi est journalisé, jamais levé."""
    try:
        await telegram_service.send_smart_alert(
            message=_ruin_message(prob_ruin, horizon_days, withdrawal_rate, ter, monthly_wd),
            chat_id=chat_id,
            user_id=user_id,
            priority="critical",
            symbol="PORTFOLIO",
            alert_type="RUIN_PROBABILITY",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ruin alert Telegram failed: %s", exc)
