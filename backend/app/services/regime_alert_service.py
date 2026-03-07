"""Regime mutation alert service.

Compares the current global market regime (via BTC proxy) with the last
known regime stored in Redis.  When a transition is detected, sends a
priority Telegram notification to every opted-in user with the updated
trading parameters (risk_multiplier, alpha_threshold, gold shield status).
"""

import logging
from typing import Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import _get_redis_txt
from app.ml.regime_detector import MarketRegimeDetector, RegimeConfig
from app.models.user import User
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)

# Redis key storing the last known regime (per-global, not per-user)
REDIS_KEY_LAST_REGIME = "regime:global:last"
# TTL for the cached regime — 24h safety net (refresh every 12h via cron)
REDIS_REGIME_TTL = 86400


class RegimeAlertService:
    """Detects regime mutations and dispatches Telegram alerts."""

    def __init__(self) -> None:
        self.detector = MarketRegimeDetector()

    async def _get_current_regime(self) -> Optional[str]:
        """Detect current global regime via BTC prices (90-day window)."""
        try:
            from app.services.data_fetcher import get_cached_history

            _, btc_prices = get_cached_history("BTC", days=90)
            if not btc_prices or len(btc_prices) < 7:
                from app.ml.historical_data import HistoricalDataFetcher

                fetcher = HistoricalDataFetcher()
                _, btc_prices = await fetcher.get_crypto_history("BTC", days=90)

            if not btc_prices or len(btc_prices) < 7:
                logger.warning("Not enough BTC price data for regime detection")
                return None

            # Fetch Fear & Greed for better accuracy
            fear_greed: Optional[int] = None
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("https://api.alternative.me/fng/?limit=1")
                    if resp.status_code == 200:
                        fear_greed = int(resp.json()["data"][0].get("value", 50))
            except Exception:
                pass

            result = self.detector.detect(btc_prices, "BTC", fear_greed)
            return result.dominant_regime
        except Exception as e:
            logger.error("Regime detection failed: %s", e)
            return None

    async def _get_last_regime(self) -> Optional[str]:
        """Read last known regime from Redis."""
        r = await _get_redis_txt()
        return await r.get(REDIS_KEY_LAST_REGIME)

    async def _set_last_regime(self, regime: str) -> None:
        """Store current regime in Redis."""
        r = await _get_redis_txt()
        await r.set(REDIS_KEY_LAST_REGIME, regime, ex=REDIS_REGIME_TTL)

    def format_mutation_alert(
        self,
        old_regime: str,
        new_regime: str,
    ) -> str:
        """Build the Telegram HTML message for a regime mutation.

        Includes: new trading parameters (risk_multiplier, alpha_threshold,
        gold shield recommendation).
        """
        old_cfg = RegimeConfig.from_regime(old_regime)
        new_cfg = RegimeConfig.from_regime(new_regime)

        # Direction arrow
        _REGIME_EMOJI = {
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
        old_emoji = _REGIME_EMOJI.get(old_regime, "⬜")
        new_emoji = _REGIME_EMOJI.get(new_regime, "⬜")

        # Gold shield recommendation
        if new_cfg.gold_relevance == "high":
            gold_status = "🛡️ Bouclier Or : <b>RENFORCER</b> (refuge prioritaire)"
        elif new_cfg.gold_relevance == "low":
            gold_status = "🪙 Bouclier Or : <b>ALLÉGER</b> (faible pertinence en expansion)"
        else:
            gold_status = "⚖️ Bouclier Or : <b>MAINTENIR</b> (neutre)"

        # Risk multiplier direction
        risk_dir = "↑" if new_cfg.risk_multiplier > old_cfg.risk_multiplier else "↓"
        if new_cfg.risk_multiplier == old_cfg.risk_multiplier:
            risk_dir = "="

        return (
            f"<b>🔄 MUTATION DE CYCLE DÉTECTÉE</b>\n\n"
            f"{old_emoji} {old_regime.upper()}  →  {new_emoji} {new_regime.upper()}\n\n"
            f"<b>Nouveaux paramètres de trading :</b>\n"
            f"• Risk Multiplier : <b>×{new_cfg.risk_multiplier}</b> {risk_dir} (était ×{old_cfg.risk_multiplier})\n"
            f"• Alpha Threshold : <b>{new_cfg.alpha_threshold}</b> (était {old_cfg.alpha_threshold})\n"
            f"• {gold_status}\n"
            f"• Mode : <b>{new_cfg.mode_label}</b>\n"
            f"• Vol Régime : {new_cfg.vol_regime}\n\n"
            f"<i>Les stratégies et tailles de DCA s'adaptent automatiquement.</i>"
        )

    async def check_and_alert(self) -> dict:
        """Main entry point: detect regime, compare with cache, alert if changed.

        Returns a summary dict for logging/monitoring.
        """
        current = await self._get_current_regime()
        if not current:
            return {"status": "skip", "reason": "detection_failed"}

        last = await self._get_last_regime()

        # First run: seed cache, no alert
        if last is None:
            await self._set_last_regime(current)
            return {"status": "seed", "regime": current}

        # No change
        if current == last:
            # Refresh TTL
            await self._set_last_regime(current)
            return {"status": "unchanged", "regime": current}

        # ── Mutation detected ──
        logger.info("Regime mutation: %s → %s", last, current)
        message = self.format_mutation_alert(last, current)

        # Send to all Telegram-enabled users
        sent_count = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(
                    User.is_active == True,  # noqa: E712
                    User.telegram_enabled == True,  # noqa: E712
                )
            )
            users = result.scalars().all()

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
                    sent_count += 1
                except Exception as e:
                    logger.error(
                        "Failed to send regime alert to user %s: %s",
                        user.id,
                        e,
                    )

        # Update cache
        await self._set_last_regime(current)

        return {
            "status": "mutation",
            "old_regime": last,
            "new_regime": current,
            "users_notified": sent_count,
        }


# Singleton
regime_alert_service = RegimeAlertService()
