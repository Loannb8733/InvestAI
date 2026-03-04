"""Telegram notification service for InvestAI smart alerts (per-user)."""

import logging
from typing import Optional

import httpx
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Cooldown: 4 hours per user per asset per alert type
COOLDOWN_TTL = 4 * 3600  # 14400 seconds

_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


class TelegramService:
    """Send smart alerts via Telegram Bot API with per-user cooldown."""

    async def _is_on_cooldown(self, key: str) -> bool:
        """Check if an alert key is within cooldown period."""
        r = await _get_redis()
        return await r.exists(key) > 0

    async def _set_cooldown(self, key: str) -> None:
        """Set cooldown for an alert key (4h TTL)."""
        r = await _get_redis()
        await r.set(key, "1", ex=COOLDOWN_TTL)

    async def send_message(self, text: str, chat_id: str, parse_mode: str = "HTML") -> bool:
        """Send a message to a specific Telegram chat."""
        if not settings.telegram_bot_enabled:
            logger.debug("Telegram bot not configured, skipping message")
            return False

        url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Telegram message sent to chat %s", chat_id)
                return True
        except httpx.HTTPStatusError as e:
            logger.error("Telegram API error %s: %s", e.response.status_code, e.response.text)
            return False
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return False

    async def send_smart_alert(
        self,
        message: str,
        chat_id: str,
        user_id: Optional[str] = None,
        priority: str = "normal",
        symbol: Optional[str] = None,
        alert_type: Optional[str] = None,
    ) -> bool:
        """Send a smart alert with per-user cooldown rate-limiting.

        Args:
            message: Alert text (HTML supported).
            chat_id: Telegram chat ID to send to.
            user_id: User ID for per-user cooldown tracking.
            priority: "low", "normal", "high", "critical".
            symbol: Asset symbol for cooldown tracking.
            alert_type: Alert type for cooldown tracking.

        Returns:
            True if sent, False if skipped (cooldown) or failed.
        """
        # Check cooldown if symbol + alert_type provided
        if symbol and alert_type:
            uid = user_id or "global"
            cooldown_key = f"tg:cooldown:{uid}:{alert_type}:{symbol}"
            if await self._is_on_cooldown(cooldown_key):
                logger.debug("Telegram alert skipped (cooldown): %s/%s/%s", uid, alert_type, symbol)
                return False

        # Priority prefix
        prefix = {
            "critical": "\U0001F6A8",  # 🚨
            "high": "\u26A0\uFE0F",  # ⚠️
            "normal": "\U0001F514",  # 🔔
            "low": "\U0001F4AC",  # 💬
        }.get(priority, "\U0001F514")

        formatted = f"{prefix} <b>InvestAI</b>\n\n{message}"

        sent = await self.send_message(formatted, chat_id=chat_id)

        # Set cooldown after successful send
        if sent and symbol and alert_type:
            uid = user_id or "global"
            await self._set_cooldown(f"tg:cooldown:{uid}:{alert_type}:{symbol}")

        return sent

    async def alert_anomaly(
        self,
        symbol: str,
        anomaly_type: str,
        severity: str,
        description: str,
        price_change_pct: float,
        chat_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Send anomaly detection alert to a user."""
        if not chat_id:
            return False

        severity_map = {
            "high": "critical",
            "medium": "high",
            "low": "normal",
        }
        priority = severity_map.get(severity, "normal")

        sign = "+" if price_change_pct > 0 else ""
        msg = (
            f"<b>Anomalie détectée — {symbol}</b>\n"
            f"Type : {anomaly_type}\n"
            f"Sévérité : {severity}\n"
            f"Variation : {sign}{price_change_pct:.1f}%\n\n"
            f"{description}"
        )

        return await self.send_smart_alert(
            message=msg,
            chat_id=chat_id,
            user_id=user_id,
            priority=priority,
            symbol=symbol,
            alert_type="anomaly",
        )

    async def alert_bottom_zone(
        self,
        symbol: str,
        current_price: float,
        estimated_bottom: float,
        confidence: float,
        distance_pct: float,
        chat_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Send alert when asset enters bottom zone with high confidence."""
        if not chat_id:
            return False

        msg = (
            f"<b>Zone de Bottom détectée — {symbol}</b>\n"
            f"Prix actuel : {current_price:,.2f} €\n"
            f"Bottom estimé : {estimated_bottom:,.2f} €\n"
            f"Distance : {distance_pct:.1f}%\n"
            f"Confiance : {confidence * 100:.0f}%\n\n"
            f"Opportunité d'achat potentielle."
        )

        return await self.send_smart_alert(
            message=msg,
            chat_id=chat_id,
            user_id=user_id,
            priority="critical",
            symbol=symbol,
            alert_type="bottom_zone",
        )


telegram_service = TelegramService()
