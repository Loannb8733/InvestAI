from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.notifications.models import Notification, NotificationPriority, NotificationType
from app.domains.predictions.models import PlannedOrder
from tests.notifications.conftest import TELEGRAM_SECRET
from tests.notifications.recording import Recorder, Telegram
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis")
BASE = "/api/v1/notifications"
WEBHOOK = "/api/v1/bot/telegram/webhook"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
CHAT = "777"


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _notify(db: AsyncSession, user: User, title: str, minutes_ago: int, **fields: Any) -> None:
    db.add(
        Notification(
            user_id=user.id,
            type=fields.pop("type", NotificationType.SYSTEM),
            title=title,
            message=f"Détail : {title}",
            priority=fields.pop("priority", NotificationPriority.NORMAL),
            created_at=FROZEN_NOW - timedelta(minutes=minutes_ago),
            **fields,
        )
    )


async def _seed_notifications(db: AsyncSession, user: User, other: User) -> str:
    await _notify(
        db,
        user,
        "Alerte: BTC au-dessus de 60000",
        5,
        type=NotificationType.ALERT_TRIGGERED,
        priority=NotificationPriority.HIGH,
        reference_type="alert",
        reference_id=uuid4(),
    )
    await _notify(db, user, "Rapport prêt", 30, type=NotificationType.REPORT_READY)
    await _notify(db, user, "Maintenance", 60, is_read=True)
    await _notify(db, other, "Notification d'un autre", 10)
    await db.commit()
    query = select(Notification.id).where(Notification.user_id == other.id)
    return str((await db.execute(query)).scalar_one())


async def _routes_flow(rec: Recorder, db: AsyncSession, user: User, other: User) -> None:
    headers = _auth(user)
    await rec.shot("list_empty", "GET", BASE, headers)
    await rec.shot("count_empty", "GET", f"{BASE}/count", headers)
    foreign = await _seed_notifications(db, user, other)
    listed = await rec.shot("list_all", "GET", BASE, headers)
    await rec.shot("list_unread", "GET", f"{BASE}?unread_only=true", headers)
    await rec.shot("list_page", "GET", f"{BASE}?limit=1&offset=1", headers)
    await rec.shot("list_limit_capped", "GET", f"{BASE}?limit=1000", headers)
    await rec.shot("count_seeded", "GET", f"{BASE}/count", headers)
    await rec.shot("read_own", "POST", f"{BASE}/{listed[0]['id']}/read", headers)
    await rec.shot("read_own_again", "POST", f"{BASE}/{listed[0]['id']}/read", headers)
    await rec.shot("read_other_user", "POST", f"{BASE}/{foreign}/read", headers)
    await rec.shot("read_unknown", "POST", f"{BASE}/{UNKNOWN_ID}/read", headers)
    await rec.shot("read_bad_id", "POST", f"{BASE}/pas-un-uuid/read", headers)
    await rec.shot("count_after_read", "GET", f"{BASE}/count", headers)
    await rec.shot("read_all", "POST", f"{BASE}/read-all", headers)
    await rec.shot("read_all_again", "POST", f"{BASE}/read-all", headers)
    await rec.shot("count_after_read_all", "GET", f"{BASE}/count", headers)
    await rec.shot("count_other_user", "GET", f"{BASE}/count", _auth(other))
    await rec.shot("list_unauthenticated", "GET", BASE, {})


async def _telegram_test_flow(
    rec: Recorder, db: AsyncSession, user: User, telegram: Telegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _auth(user)
    with monkeypatch.context() as off:
        off.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
        await rec.shot("telegram_test_bot_off", "POST", f"{BASE}/telegram/test", headers)
    await rec.shot("telegram_test_user_not_linked", "POST", f"{BASE}/telegram/test", headers)
    user.telegram_enabled = True
    user.telegram_chat_id = CHAT
    await db.commit()
    await rec.shot("telegram_test_sent", "POST", f"{BASE}/telegram/test", headers)
    telegram.failing = True
    await rec.shot("telegram_test_refused", "POST", f"{BASE}/telegram/test", headers)
    telegram.failing = False
    await rec.shot("telegram_test_unauthenticated", "POST", f"{BASE}/telegram/test", {})


@pytest.mark.usefixtures("offline")
async def test_notification_routes_match_golden(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    admin_user: User,
    telegram: Telegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = Recorder(client, telegram)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _routes_flow(rec, db_session, regular_user, admin_user)
        await _telegram_test_flow(rec, db_session, regular_user, telegram, monkeypatch)
    assert not rec.mismatches, f"golden notifications différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


def _callback(data: str, chat: str = CHAT, callback_id: str = "cb-1") -> dict[str, Any]:
    return {"callback_query": {"id": callback_id, "data": data, "message": {"chat": {"id": chat}, "message_id": 9}}}


async def _webhook_guards(rec: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    signed = {"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_SECRET}
    with monkeypatch.context() as off:
        off.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
        await rec.shot("webhook_bot_off", "POST", WEBHOOK, signed, _callback("plan_order:alpha:x:BTC:10"))
    with monkeypatch.context() as unsigned:
        unsigned.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        await rec.shot("webhook_no_secret_configured", "POST", WEBHOOK, signed, _callback("x"))
    await rec.shot("webhook_without_secret", "POST", WEBHOOK, {}, _callback("x"))
    await rec.shot("webhook_wrong_secret", "POST", WEBHOOK, {"X-Telegram-Bot-Api-Secret-Token": "faux"}, {})
    await rec.shot("webhook_not_json", "POST", WEBHOOK, signed, content=b"{pas du json")
    await rec.shot("webhook_not_a_callback", "POST", WEBHOOK, signed, {"message": {"text": "/start"}})


async def _webhook_callbacks(rec: Recorder, user: User) -> None:
    signed = {"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_SECRET}
    uid = str(user.id)
    cases = {
        "webhook_empty_data": _callback(""),
        "webhook_too_short": _callback("sim_ruin:x"),
        "webhook_not_alpha": _callback(f"sim_ruin:beta:{uid}:BTC:10"),
        "webhook_bad_amount": _callback(f"sim_ruin:alpha:{uid}:BTC:beaucoup"),
        "webhook_wrong_chat": _callback(f"plan_order:alpha:{uid}:BTC:10", chat="999"),
        "webhook_unknown_user": _callback(f"plan_order:alpha:{UNKNOWN_ID}:BTC:10"),
        "webhook_unknown_action": _callback(f"vendre:alpha:{uid}:BTC:10"),
        "webhook_plan_order": _callback(f"plan_order:alpha:{uid}:SOL:250.5"),
        "webhook_simulate_ruin": _callback(f"sim_ruin:alpha:{uid}:BTC:500"),
        "webhook_simulate_ruin_too_soon": _callback(f"sim_ruin:alpha:{uid}:BTC:500", callback_id="cb-2"),
    }
    for name, body in cases.items():
        await rec.shot(name, "POST", WEBHOOK, signed, body)


@pytest.mark.usefixtures("offline", "live_quotes")
async def test_telegram_webhook_matches_golden(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    telegram: Telegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = Recorder(client, telegram)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, _auth(regular_user))
        regular_user.telegram_enabled = True
        regular_user.telegram_chat_id = CHAT
        await db_session.commit()
        await _webhook_guards(rec, monkeypatch)
        await _webhook_callbacks(rec, regular_user)
    orders = (await db_session.execute(select(PlannedOrder))).scalars().all()
    columns = ("symbol", "action", "order_eur", "source", "status", "notes", "alpha_score", "regime")
    rec.check("webhook_planned_orders", [{c: getattr(o, c) for c in columns} for o in orders])
    assert not rec.mismatches, f"golden webhook Telegram différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
