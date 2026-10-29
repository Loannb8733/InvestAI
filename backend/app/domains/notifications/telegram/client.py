import json
import logging
from typing import Any, cast

import httpx
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.redis_client import redis_async_url, redis_client_kwargs
from app.domains.notifications.telegram.messages import anomaly_text, bottom_zone_text, smart_alert_text

logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://api.telegram.org/bot{token}/{method}"
COOLDOWN_TTL = 4 * 3600
SEVERITY_PRIORITIES = {"high": "critical", "medium": "high", "low": "normal"}

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Client Redis partagé du bot : pauses entre alertes et limite des simulations."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())
    return _redis


def _cooldown_key(user_id: str | None, alert_type: str, symbol: str) -> str:
    return f"tg:cooldown:{user_id or 'global'}:{alert_type}:{symbol}"


def _with_markup(payload: dict[str, Any], reply_markup: dict[str, Any] | None) -> dict[str, Any]:
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return payload


class TelegramService:
    """Bot Telegram : messages, réponses aux boutons, et alertes espacées d'au moins quatre heures."""

    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=10.0)
        return cls._client

    async def _post(self, method: str, payload: dict[str, Any]) -> httpx.Response:
        url = TELEGRAM_BASE.format(token=settings.TELEGRAM_BOT_TOKEN, method=method)
        response = await self._get_client().post(url, json=payload)
        response.raise_for_status()
        return response

    async def _is_on_cooldown(self, key: str) -> bool:
        """Sans Redis joignable, rend False : mieux vaut un doublon qu'une alerte de prix passée sous silence."""
        try:
            return bool(await (await get_redis()).exists(key) > 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pause d'alerte illisible, le message part quand même : %s", exc)
            return False

    async def _set_cooldown(self, key: str, ttl: int = COOLDOWN_TTL) -> None:
        try:
            await (await get_redis()).set(key, "1", ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pause d'alerte non posée : %s", exc)

    async def send_message(
        self, text: str, chat_id: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Envoie un message HTML ; rend le message Telegram, ou None si le bot est absent ou l'envoi refusé."""
        if not settings.telegram_bot_enabled:
            logger.debug("Telegram bot not configured, skipping message")
            return None
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            response = await self._post("sendMessage", _with_markup(payload, reply_markup))
            logger.info("Telegram message sent to chat %s", chat_id)
            return cast(dict[str, Any] | None, response.json().get("result"))
        except httpx.HTTPStatusError as exc:
            logger.error("Telegram API error %s: %s", exc.response.status_code, exc.response.text)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed: %s", exc)
            return None

    async def edit_message(
        self, chat_id: str, message_id: int | None, text: str, reply_markup: dict[str, Any] | None = None
    ) -> bool:
        if not settings.telegram_bot_enabled:
            return False
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            await self._post("editMessageText", _with_markup(payload, reply_markup))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram edit failed: %s", exc)
            return False

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> bool:
        """Répond à l'appui sur un bouton, ce qui retire l'indicateur de chargement côté Telegram."""
        if not settings.telegram_bot_enabled:
            return False
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        try:
            await self._post("answerCallbackQuery", payload)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram answer_callback failed: %s", exc)
            return False

    async def send_smart_alert(
        self,
        message: str,
        chat_id: str,
        user_id: str | None = None,
        priority: str = "normal",
        symbol: str | None = None,
        alert_type: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Alerte préfixée par sa priorité ; avec symbole et type, une seule par utilisateur et par 4 h."""
        key = _cooldown_key(user_id, alert_type, symbol) if symbol and alert_type else None
        if key and await self._is_on_cooldown(key):
            logger.debug("Telegram alert skipped (cooldown): %s", key)
            return None
        result = await self.send_message(smart_alert_text(message, priority), chat_id, reply_markup)
        if result and key:
            await self._set_cooldown(key)
        return result

    async def alert_anomaly(
        self,
        symbol: str,
        anomaly_type: str,
        severity: str,
        description: str,
        price_change_pct: float,
        chat_id: str = "",
        user_id: str | None = None,
    ) -> bool:
        """Alerte d'anomalie de marché ; la priorité suit la sévérité. Rend True si le message est parti."""
        if not chat_id:
            return False
        result = await self.send_smart_alert(
            anomaly_text(symbol, anomaly_type, severity, description, price_change_pct),
            chat_id,
            user_id,
            SEVERITY_PRIORITIES.get(severity, "normal"),
            symbol,
            "anomaly",
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
        user_id: str | None = None,
    ) -> bool:
        """Alerte critique d'entrée en zone de creux. Rend True si le message est parti."""
        if not chat_id:
            return False
        result = await self.send_smart_alert(
            bottom_zone_text(symbol, current_price, estimated_bottom, confidence, distance_pct),
            chat_id,
            user_id,
            "critical",
            symbol,
            "bottom_zone",
        )
        return result is not None


telegram_service = TelegramService()
