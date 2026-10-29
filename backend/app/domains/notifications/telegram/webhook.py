import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.session import session_factory
from app.domains.identity.models import User
from app.domains.notifications.telegram.callbacks import Callback, plan_order, simulate_ruin
from app.domains.notifications.telegram.client import telegram_service

logger = logging.getLogger(__name__)

router = APIRouter()

_users = User.__table__
HANDLERS = {"sim_ruin": simulate_ruin, "plan_order": plan_order}


def _ok() -> JSONResponse:
    return JSONResponse({"ok": True})


def _refusal(secret_token: str | None) -> JSONResponse | None:
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        logger.error(
            "Webhook Telegram refusé : le bot est actif mais TELEGRAM_WEBHOOK_SECRET "
            "n'est pas défini. Sans ce secret, n'importe qui peut appeler ce endpoint."
        )
        return JSONResponse({"ok": False}, status_code=403)
    if not hmac.compare_digest(secret_token or "", settings.TELEGRAM_WEBHOOK_SECRET):
        logger.warning("Telegram webhook rejected: invalid or missing secret token")
        return JSONResponse({"ok": False}, status_code=403)
    return None


def _parse(callback_query: dict[str, Any]) -> Callback | str:
    callback_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not data or not chat_id:
        return "Données invalides"
    parts = data.split(":")
    if len(parts) < 5 or parts[1] != "alpha":
        return "Format invalide"
    try:
        order_eur = float(parts[4])
    except ValueError:
        return "Montant invalide"
    return Callback(callback_id, chat_id, message.get("message_id"), parts[0], parts[2], parts[3], order_eur)


async def _chat_belongs_to_user(db: AsyncSession, user_id: str, chat_id: str) -> bool:
    query = select(_users.c.telegram_enabled, _users.c.telegram_chat_id).where(_users.c.id == user_id)
    row = (await db.execute(query)).first()
    return bool(row and row.telegram_enabled and row.telegram_chat_id and str(row.telegram_chat_id) == chat_id)


async def _dispatch(callback: Callback) -> None:
    async with session_factory() as db:
        if not await _chat_belongs_to_user(db, callback.user_id, callback.chat_id):
            logger.warning(
                "Telegram callback rejected: chat_id %s doesn't match user %s", callback.chat_id, callback.user_id
            )
            await telegram_service.answer_callback_query(callback.callback_id, "Accès refusé", show_alert=True)
            return
        handler = HANDLERS.get(callback.action)
        if handler is None:
            await telegram_service.answer_callback_query(callback.callback_id, "Action inconnue")
            return
        await handler(db, callback)


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
) -> JSONResponse:
    """Boutons des alertes Telegram : simulation de ruine et planification d'ordre, pour le seul chat de l'utilisateur.

    L'appel doit porter le secret du webhook ; toute autre mise à jour que l'appui sur un bouton est ignorée.
    """
    if not settings.telegram_bot_enabled:
        return _ok()
    refusal = _refusal(x_telegram_bot_api_secret_token)
    if refusal is not None:
        return refusal
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _ok()
    callback_query = body.get("callback_query")
    if not callback_query:
        return _ok()
    parsed = _parse(callback_query)
    if isinstance(parsed, str):
        await telegram_service.answer_callback_query(callback_query.get("id", ""), parsed)
        return _ok()
    await _dispatch(parsed)
    return _ok()
