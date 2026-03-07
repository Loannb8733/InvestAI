"""Telegram Bot webhook handler for interactive callbacks.

Handles:
- sim_ruin:{user_id}:{symbol}:{order_eur} — Run Monte Carlo simulation
- plan_order:{user_id}:{symbol}:{order_eur} — Create a planned order

Security:
- Validates chat_id matches the user's registered telegram_chat_id
- Rate-limits Monte Carlo callbacks (30s per user)
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.planned_order import PlannedOrder, PlannedOrderStatus
from app.models.user import User
from app.services.telegram_service import MC_CALLBACK_TTL, _get_redis, telegram_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """Fetch user by UUID string."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _verify_chat_id(db: AsyncSession, user_id: str, chat_id: str) -> bool:
    """Verify that the callback's chat_id matches the user's registered chat_id."""
    user = await _get_user_by_id(db, user_id)
    if not user:
        return False
    return user.telegram_enabled and user.telegram_chat_id and str(user.telegram_chat_id) == str(chat_id)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates (callback_query only)."""
    if not settings.telegram_bot_enabled:
        return JSONResponse({"ok": True})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    callback_query = body.get("callback_query")
    if not callback_query:
        # Not a callback — ignore (we only handle button presses)
        return JSONResponse({"ok": True})

    callback_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    message_id = message.get("message_id")

    if not data or not chat_id:
        await telegram_service.answer_callback_query(callback_id, "Données invalides")
        return JSONResponse({"ok": True})

    # Parse callback data: action:user_id:symbol:order_eur
    parts = data.split(":")
    if len(parts) < 4:
        await telegram_service.answer_callback_query(callback_id, "Format invalide")
        return JSONResponse({"ok": True})

    action = parts[0]
    # Reconstruct: action is first part, then "alpha", user_id, symbol, order_eur
    # Format: sim_ruin:alpha:{user_id}:{symbol}:{order_eur}
    # or: plan_order:alpha:{user_id}:{symbol}:{order_eur}
    if len(parts) < 5 or parts[1] != "alpha":
        await telegram_service.answer_callback_query(callback_id, "Format invalide")
        return JSONResponse({"ok": True})

    user_id = parts[2]
    symbol = parts[3]
    try:
        order_eur = float(parts[4])
    except ValueError:
        await telegram_service.answer_callback_query(callback_id, "Montant invalide")
        return JSONResponse({"ok": True})

    # Security: verify chat_id matches user
    async with AsyncSessionLocal() as db:
        if not await _verify_chat_id(db, user_id, chat_id):
            logger.warning(
                "Telegram callback rejected: chat_id %s doesn't match user %s",
                chat_id,
                user_id,
            )
            await telegram_service.answer_callback_query(
                callback_id,
                "Accès refusé",
                show_alert=True,
            )
            return JSONResponse({"ok": True})

        if action == "sim_ruin":
            await _handle_simulate_ruin(
                db,
                callback_id,
                chat_id,
                message_id,
                user_id,
                symbol,
                order_eur,
            )
        elif action == "plan_order":
            await _handle_plan_order(
                db,
                callback_id,
                chat_id,
                message_id,
                user_id,
                symbol,
                order_eur,
            )
        else:
            await telegram_service.answer_callback_query(callback_id, "Action inconnue")

    return JSONResponse({"ok": True})


async def _handle_simulate_ruin(
    db: AsyncSession,
    callback_id: str,
    chat_id: str,
    message_id: int,
    user_id: str,
    symbol: str,
    order_eur: float,
) -> None:
    """Run Monte Carlo before/after and edit the message with results."""
    # Rate limiting: 30s per user
    r = await _get_redis()
    rate_key = f"tg:mc_rate:{user_id}"
    if await r.exists(rate_key):
        await telegram_service.answer_callback_query(
            callback_id,
            "Simulation en cours, patientez 30s...",
            show_alert=True,
        )
        return

    await r.set(rate_key, "1", ex=MC_CALLBACK_TTL)

    # Acknowledge the button press immediately
    await telegram_service.answer_callback_query(callback_id, "Simulation Monte Carlo en cours...")

    try:
        from app.services.analytics_service import analytics_service
        from app.services.smart_insights_service import smart_insights_service

        # Derive vol_regime from market regime
        _vol_regime = await smart_insights_service.get_current_vol_regime(db, user_id)

        # Monte Carlo BEFORE
        mc_before = await analytics_service.monte_carlo(
            db,
            user_id,
            horizon_days=90,
            num_simulations=2000,
            vol_regime=_vol_regime,
        )
        prob_ruin_before = mc_before.prob_ruin

        # Monte Carlo AFTER (with contribution)
        contribution = {symbol: order_eur} if order_eur > 0 else None
        mc_after = await analytics_service.monte_carlo(
            db,
            user_id,
            horizon_days=90,
            num_simulations=2000,
            contribution=contribution,
            vol_regime=_vol_regime,
        )
        prob_ruin_after = mc_after.prob_ruin

        # Determine verdict
        ruin_delta = prob_ruin_after - prob_ruin_before
        if ruin_delta < -1:
            verdict = "SÉCURISÉ"
            emoji = "\u2705"  # ✅
        elif ruin_delta > 1:
            verdict = "RISQUÉ"
            emoji = "\u26A0\uFE0F"  # ⚠️
        else:
            verdict = "NEUTRE"
            emoji = "\U0001F7F0"  # 🟰

        # Edit the original message to append the simulation result
        result_text = (
            f"\n\n📊 <b>Simulation Monte Carlo</b>\n"
            f"Ruine: <b>{prob_ruin_before:.1f}%</b> ➡️ <b>{prob_ruin_after:.1f}%</b>\n"
            f"Rendement: {mc_before.expected_return:.1f}% ➡️ {mc_after.expected_return:.1f}%\n"
            f"P(positif): {mc_before.prob_positive:.1f}% ➡️ {mc_after.prob_positive:.1f}%\n\n"
            f"{emoji} Verdict: <b>{verdict}</b>"
        )

        # Since we can't easily get original text, we edit with the new text
        new_text = (
            f"\u26A0\uFE0F <b>InvestAI</b>\n\n"
            f"🚀 <b>Signal Alpha : {symbol}</b>\n"
            f"Ordre suggéré: <b>{order_eur:,.2f} €</b>"
            f"{result_text}"
        )

        # Keep the "Marquer comme Planifié" button
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "\u2705 Marquer comme Planifié",
                        "callback_data": f"plan_order:alpha:{user_id}:{symbol}:{order_eur}",
                    },
                ]
            ]
        }

        await telegram_service.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup=keyboard,
        )

    except Exception as exc:
        logger.error("Monte Carlo callback failed for %s/%s: %s", user_id, symbol, exc)
        await telegram_service.send_message(
            f"Erreur lors de la simulation: {exc}",
            chat_id=chat_id,
        )


async def _handle_plan_order(
    db: AsyncSession,
    callback_id: str,
    chat_id: str,
    message_id: int,
    user_id: str,
    symbol: str,
    order_eur: float,
) -> None:
    """Create a planned order in the database."""
    await telegram_service.answer_callback_query(callback_id, "Ordre planifié !")

    try:
        # Create the planned order
        planned = PlannedOrder(
            user_id=user_id,
            symbol=symbol,
            action="ACHAT",
            order_eur=order_eur,
            source="telegram",
            status=PlannedOrderStatus.PENDING,
            notes=f"Planifié via Telegram (chat {chat_id})",
        )
        db.add(planned)
        await db.commit()

        # Edit message to confirm
        new_text = (
            f"\u26A0\uFE0F <b>InvestAI</b>\n\n"
            f"🚀 <b>Signal Alpha : {symbol}</b>\n"
            f"Ordre suggéré: <b>{order_eur:,.2f} €</b>\n\n"
            f"\u2705 <b>Ordre planifié !</b>\n"
            f"Visible dans votre Matrice de Stratégie."
        )

        # Remove all buttons (order is confirmed)
        await telegram_service.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup={"inline_keyboard": []},
        )

    except Exception as exc:
        logger.error("Plan order callback failed for %s/%s: %s", user_id, symbol, exc)
        await telegram_service.send_message(
            f"Erreur lors de la planification: {exc}",
            chat_id=chat_id,
        )
