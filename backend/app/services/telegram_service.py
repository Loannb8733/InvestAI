"""Telegram notification service for InvestAI smart alerts (per-user).

Supports:
- One-way push alerts with cooldown
- InlineKeyboard buttons for interactive callbacks
- Message editing for callback responses
"""

import json
import logging
from typing import Dict, List, Optional

import httpx
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://api.telegram.org/bot{token}"
TELEGRAM_SEND = TELEGRAM_BASE + "/sendMessage"
TELEGRAM_EDIT = TELEGRAM_BASE + "/editMessageText"
TELEGRAM_ANSWER_CALLBACK = TELEGRAM_BASE + "/answerCallbackQuery"

# Cooldown: 4 hours per user per asset per alert type
COOLDOWN_TTL = 4 * 3600  # 14400 seconds

# Rate limit for Monte Carlo callbacks: 1 per 30s per user
MC_CALLBACK_TTL = 30

_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _build_inline_keyboard(buttons: List[List[Dict]]) -> Dict:
    """Build Telegram InlineKeyboardMarkup from a list of button rows.

    Each button: {"text": "Label", "callback_data": "payload"}
    """
    return {"inline_keyboard": buttons}


class TelegramService:
    """Send smart alerts via Telegram Bot API with per-user cooldown."""

    async def _is_on_cooldown(self, key: str) -> bool:
        """Check if an alert key is within cooldown period."""
        r = await _get_redis()
        return await r.exists(key) > 0

    async def _set_cooldown(self, key: str, ttl: int = COOLDOWN_TTL) -> None:
        """Set cooldown for an alert key."""
        r = await _get_redis()
        await r.set(key, "1", ex=ttl)

    async def send_message(
        self,
        text: str,
        chat_id: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Send a message to a specific Telegram chat.

        Returns the Telegram message dict on success, None on failure.
        """
        if not settings.telegram_bot_enabled:
            logger.debug("Telegram bot not configured, skipping message")
            return None

        url = TELEGRAM_SEND.format(token=settings.TELEGRAM_BOT_TOKEN)
        payload: Dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Telegram message sent to chat %s", chat_id)
                data = resp.json()
                return data.get("result")
        except httpx.HTTPStatusError as e:
            logger.error("Telegram API error %s: %s", e.response.status_code, e.response.text)
            return None
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return None

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None,
    ) -> bool:
        """Edit an existing Telegram message."""
        if not settings.telegram_bot_enabled:
            return False

        url = TELEGRAM_EDIT.format(token=settings.TELEGRAM_BOT_TOKEN)
        payload: Dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error("Telegram edit failed: %s", e)
            return False

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Answer a Telegram callback query (removes loading indicator)."""
        if not settings.telegram_bot_enabled:
            return False

        url = TELEGRAM_ANSWER_CALLBACK.format(token=settings.TELEGRAM_BOT_TOKEN)
        payload: Dict = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error("Telegram answer_callback failed: %s", e)
            return False

    async def send_smart_alert(
        self,
        message: str,
        chat_id: str,
        user_id: Optional[str] = None,
        priority: str = "normal",
        symbol: Optional[str] = None,
        alert_type: Optional[str] = None,
        reply_markup: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Send a smart alert with per-user cooldown rate-limiting.

        Returns the Telegram message dict on success, None if skipped or failed.
        """
        # Check cooldown if symbol + alert_type provided
        if symbol and alert_type:
            uid = user_id or "global"
            cooldown_key = f"tg:cooldown:{uid}:{alert_type}:{symbol}"
            if await self._is_on_cooldown(cooldown_key):
                logger.debug("Telegram alert skipped (cooldown): %s/%s/%s", uid, alert_type, symbol)
                return None

        # Priority prefix
        prefix = {
            "critical": "\U0001F6A8",  # 🚨
            "high": "\u26A0\uFE0F",  # ⚠️
            "normal": "\U0001F514",  # 🔔
            "low": "\U0001F4AC",  # 💬
        }.get(priority, "\U0001F514")

        formatted = f"{prefix} <b>InvestAI</b>\n\n{message}"

        result = await self.send_message(
            formatted,
            chat_id=chat_id,
            reply_markup=reply_markup,
        )

        # Set cooldown after successful send
        if result and symbol and alert_type:
            uid = user_id or "global"
            await self._set_cooldown(f"tg:cooldown:{uid}:{alert_type}:{symbol}")

        return result

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

        result = await self.send_smart_alert(
            message=msg,
            chat_id=chat_id,
            user_id=user_id,
            priority=priority,
            symbol=symbol,
            alert_type="anomaly",
        )
        return result is not None

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

        result = await self.send_smart_alert(
            message=msg,
            chat_id=chat_id,
            user_id=user_id,
            priority="critical",
            symbol=symbol,
            alert_type="bottom_zone",
        )
        return result is not None

    # ── Regime-aware message formatting ─────────────────────────────

    @staticmethod
    def format_regime_alert(
        symbol: str,
        action: str,
        regime: str,
        description: str,
    ) -> str:
        """Format a strategy alert with tone adapted to market regime.

        Bear/bottom phases → cautious, opportunity-focused tone.
        Bull/markup phases → momentum, expansion tone.
        Top/distribution phases → prudence, take-profits tone.
        """
        _REGIME_TONE = {
            "bottoming": (
                "\U0001F50E Opportunité de Creux détectée",
                "Zone sécurisée pour accumulation progressive.",
            ),
            "accumulation": (
                "\U0001F4C8 Signal d'Accumulation",
                "Phase d'entrée progressive — Smart Money en action.",
            ),
            "markup": (
                "\U0001F680 Signal de Momentum confirmé",
                "Phase d'Expansion — laissez courir vos positions.",
            ),
            "topping": (
                "\u26A0\uFE0F Surchauffe détectée",
                "Prudence — sécurisez une partie de vos gains.",
            ),
            "distribution": (
                "\U0001F6A8 Phase de Distribution",
                "Prenez vos profits avant le retournement.",
            ),
            "markdown": (
                "\U0001F4C9 Marché en Markdown",
                "Patience — attendez les signaux de creux pour accumuler.",
            ),
            # Backward-compat 4-phase
            "bottom": (
                "\U0001F50E Opportunité de Creux détectée",
                "Zone sécurisée pour accumulation progressive.",
            ),
            "bearish": (
                "\U0001F4C9 Marché Baissier",
                "Conservation recommandée — préparez votre watchlist.",
            ),
            "bullish": (
                "\U0001F680 Signal de Momentum confirmé",
                "Phase d'Expansion — conditions favorables.",
            ),
            "top": (
                "\u26A0\uFE0F Sommet potentiel",
                "Prudence — sécurisez vos gains.",
            ),
        }

        tone_title, tone_hint = _REGIME_TONE.get(
            regime,
            ("\U0001F514 Alerte Stratégie", ""),
        )

        return f"<b>{tone_title} — {symbol}</b>\n" f"Action : {action}\n" f"{description}\n\n" f"<i>{tone_hint}</i>"

    # ── InlineKeyboard helpers ──────────────────────────────────────

    @staticmethod
    def build_alpha_keyboard(user_id: str, symbol: str, order_eur: float) -> Dict:
        """Build InlineKeyboard for TOP_ALPHA alerts with action buttons."""
        callback_prefix = f"alpha:{user_id}:{symbol}:{order_eur}"
        return _build_inline_keyboard(
            [
                [
                    {"text": "\U0001F50D Simuler Impact Ruine", "callback_data": f"sim_ruin:{callback_prefix}"},
                    {"text": "\u2705 Marquer comme Planifié", "callback_data": f"plan_order:{callback_prefix}"},
                ]
            ]
        )


telegram_service = TelegramService()
