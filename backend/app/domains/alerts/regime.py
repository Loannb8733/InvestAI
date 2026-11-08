import logging
from typing import Any

from sqlalchemy import select

from app.core.db.session import session_factory
from app.core.redis_client import _get_redis_txt
from app.domains.identity.models import User
from app.domains.market_data.fear_greed import fetch_fear_greed_index
from app.domains.market_data.history.reader import local_series
from app.domains.notifications.telegram.client import telegram_service
from app.ml.regime_detector import MarketRegimeDetector, RegimeConfig

logger = logging.getLogger(__name__)

REGIME_KEY = "regime:global:last"
REGIME_TTL_S = 86400
WINDOW_DAYS = 90
MIN_PRICES = 7
REGIME_EMOJI = {
    "bearish": "🧊",
    "markdown": "📉",
    "distribution": "🚨",
    "bottom": "🔎",
    "bottoming": "🔎",
    "accumulation": "📈",
    "bullish": "🚀",
    "markup": "🚀",
    "topping": "⚠️",
    "top": "⚠️",
}
GOLD_SHIELD = {
    "high": "🛡️ Bouclier Or : <b>RENFORCER</b> (refuge prioritaire)",
    "low": "🪙 Bouclier Or : <b>ALLÉGER</b> (faible pertinence en expansion)",
}
NEUTRAL_GOLD_SHIELD = "⚖️ Bouclier Or : <b>MAINTENIR</b> (neutre)"

_detector = MarketRegimeDetector()


async def current_regime() -> str | None:
    """Régime dominant du marché, lu sur 90 jours de cours BTC ; None sans données ou si la détection échoue."""
    try:
        btc_prices = (await local_series("BTC", WINDOW_DAYS)).prices
        if len(btc_prices) < MIN_PRICES:
            logger.warning("Not enough BTC price data for regime detection")
            return None
        fear_greed = await fetch_fear_greed_index(timeout=10.0)
        return _detector.detect(btc_prices, "BTC", fear_greed).dominant_regime
    except Exception as exc:  # noqa: BLE001
        logger.error("Regime detection failed: %s", exc)
        return None


async def last_regime() -> str | None:
    """Dernier régime mémorisé ; None au premier passage et quand Redis est injoignable, ce qui amorce sans alerter."""
    try:
        stored = await (await _get_redis_txt()).get(REGIME_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mémoire du régime injoignable (aucune alerte ne sera émise) : %s", exc)
        return None
    return str(stored) if stored is not None else None


async def remember_regime(regime: str) -> None:
    """Mémorise le régime pour 24 h ; un échec est journalisé, la passe suivante réamorcera."""
    try:
        await (await _get_redis_txt()).set(REGIME_KEY, regime, ex=REGIME_TTL_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mémoire du régime non écrite : %s", exc)


def _risk_direction(old: RegimeConfig, new: RegimeConfig) -> str:
    if new.risk_multiplier == old.risk_multiplier:
        return "="
    return "↑" if new.risk_multiplier > old.risk_multiplier else "↓"


def mutation_message(old_regime: str, new_regime: str) -> str:
    """Message Telegram HTML d'un changement de régime, avec les nouveaux paramètres de trading."""
    old_cfg = RegimeConfig.from_regime(old_regime)
    new_cfg = RegimeConfig.from_regime(new_regime)
    old_emoji = REGIME_EMOJI.get(old_regime, "⬜")
    new_emoji = REGIME_EMOJI.get(new_regime, "⬜")
    gold_status = GOLD_SHIELD.get(new_cfg.gold_relevance, NEUTRAL_GOLD_SHIELD)
    risk_dir = _risk_direction(old_cfg, new_cfg)
    return (
        f"<b>🔄 MUTATION DE CYCLE DÉTECTÉE</b>\n\n"
        f"{old_emoji} {old_regime.upper()}  →  {new_emoji} {new_regime.upper()}\n\n"
        f"<b>Nouveaux paramètres de trading :</b>\n"
        f"• Risk Multiplier : <b>×{new_cfg.risk_multiplier}</b> {risk_dir} (était ×{old_cfg.risk_multiplier})\n"  # noqa: RUF001
        f"• Alpha Threshold : <b>{new_cfg.alpha_threshold}</b> (était {old_cfg.alpha_threshold})\n"
        f"• {gold_status}\n"
        f"• Mode : <b>{new_cfg.mode_label}</b>\n"
        f"• Vol Régime : {new_cfg.vol_regime}\n\n"
        f"<i>Les stratégies et tailles de DCA s'adaptent automatiquement.</i>"
    )


async def _notify(message: str) -> int:
    sent = 0
    async with session_factory() as db:
        users = (
            await db.execute(select(User).where(User.is_active.is_(True), User.telegram_enabled.is_(True)))
        ).scalars()
        for user in users:
            if not user.telegram_chat_id:
                continue
            try:
                await telegram_service.send_smart_alert(
                    message=message,
                    chat_id=user.telegram_chat_id,
                    user_id=str(user.id),
                    priority="critical",
                    symbol="MARKET",
                    alert_type="regime_mutation",
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to send regime alert to user %s: %s", user.id, exc)
    return sent


async def check_regime_mutation() -> dict[str, Any]:
    """Compare le régime du marché au dernier mémorisé et alerte sur Telegram quand il change."""
    current = await current_regime()
    if not current:
        return {"status": "skip", "reason": "detection_failed"}
    last = await last_regime()
    if last is None:
        await remember_regime(current)
        return {"status": "seed", "regime": current}
    if current == last:
        await remember_regime(current)
        return {"status": "unchanged", "regime": current}
    logger.info("Regime mutation: %s → %s", last, current)
    sent = await _notify(mutation_message(last, current))
    await remember_regime(current)
    return {"status": "mutation", "old_regime": last, "new_regime": current, "users_notified": sent}
