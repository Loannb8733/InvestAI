from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.notifications import tasks as notification_tasks
from app.domains.notifications.models import Notification, NotificationPriority, NotificationType
from app.domains.notifications.report_mailer import report_mailer
from app.domains.notifications.repository import NotificationRepository
from app.domains.notifications.service import NotificationService
from app.domains.notifications.telegram.client import telegram_service
from app.domains.notifications.telegram.messages import alpha_keyboard
from tests.conftest import TestSessionLocal
from tests.notifications.recording import Mailbox, Recorder, Telegram
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis")
ALERT_ID = UUID("11111111-1111-1111-1111-111111111111")


async def _rows(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    query = select(Notification).where(Notification.user_id == user.id).order_by(Notification.title)
    columns = ("type", "title", "message", "priority", "reference_type", "reference_id", "is_read")
    return [{c: getattr(n, c) for c in columns} for n in (await db.execute(query)).scalars()]


async def test_notifications_match_golden(
    db_session: AsyncSession, regular_user: User, mailbox: Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder()
    uid = regular_user.id
    service = NotificationService(NotificationRepository(db_session))
    for priority in (NotificationPriority.NORMAL, NotificationPriority.HIGH, NotificationPriority.URGENT):
        await service.send(uid, NotificationType.SYSTEM, f"Priorité {priority.value}", "Corps du message", priority)
    rec.check("notify_with_email", {"mails": mailbox.drain(), "rows": await _rows(db_session, regular_user)})
    await service.send(uid, NotificationType.PORTFOLIO_UPDATE, "Courriel seul", "Sans notification", send_in_app=False)
    await service.send_alert(uid, "BTC > 60k", "Seuil franchi", ALERT_ID)
    rec.check("notify_alert", {"mails": mailbox.drain(), "rows": await _rows(db_session, regular_user)})
    with monkeypatch.context() as off:
        off.setattr(settings, "SMTP_HOST", "")
        created = await service.send(uid, NotificationType.SYSTEM, "Sans SMTP", "Aucun courriel")
    rec.check("notify_without_smtp", {"mails": mailbox.drain(), "returned": created is not None})
    assert not rec.mismatches, f"golden notifications différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


async def _smart_alerts(rec: Recorder, telegram: Telegram) -> None:
    for priority in ("critical", "high", "normal", "low", "autre"):
        await telegram_service.send_smart_alert(f"Message {priority}", chat_id="777", priority=priority)
    rec.check("telegram_priorities", telegram.drain())
    first = await telegram_service.send_smart_alert("Premier", "777", user_id="u1", symbol="BTC", alert_type="dip")
    second = await telegram_service.send_smart_alert("Second", "777", user_id="u1", symbol="BTC", alert_type="dip")
    other = await telegram_service.send_smart_alert("Autre actif", "777", user_id="u1", symbol="ETH", alert_type="dip")
    results = {"first": first, "second": second, "other": other}
    rec.check("telegram_cooldown", {"results": results, "calls": telegram.drain()})


async def _typed_alerts(rec: Recorder, telegram: Telegram) -> None:
    anomalies = [
        await telegram_service.alert_anomaly("BTC", "volume", "high", "Volume x5", 12.34, chat_id="777"),
        await telegram_service.alert_anomaly("ETH", "prix", "medium", "Chute brutale", -8.0, chat_id="777"),
        await telegram_service.alert_anomaly("SOL", "prix", "low", "Léger écart", 0.0, chat_id="777", user_id="u2"),
        await telegram_service.alert_anomaly("DOGE", "prix", "low", "Sans destinataire", 1.0),
    ]
    rec.check("telegram_anomalies", {"results": anomalies, "calls": telegram.drain()})
    bottoms = [
        await telegram_service.alert_bottom_zone("BTC", 58000.5, 55000.0, 0.82, 5.45, chat_id="777"),
        await telegram_service.alert_bottom_zone("ETH", 2000.0, 1800.0, 0.5, 11.1),
    ]
    rec.check("telegram_bottom_zones", {"results": bottoms, "calls": telegram.drain()})
    rec.check("telegram_alpha_keyboard", alpha_keyboard("u1", "SOL", 250.5))


async def test_telegram_alerts_match_golden(telegram: Telegram, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder()
    await _smart_alerts(rec, telegram)
    await _typed_alerts(rec, telegram)
    with monkeypatch.context() as off:
        off.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
        silent = {
            "send": await telegram_service.send_message("x", "777"),
            "edit": await telegram_service.edit_message("777", 9, "x"),
            "answer": await telegram_service.answer_callback_query("cb", "x"),
        }
    rec.check("telegram_bot_off", {"results": silent, "calls": telegram.drain()})
    assert not rec.mismatches, f"golden alertes Telegram différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


async def _report_mails(rec: Recorder, mailbox: Mailbox) -> None:
    top = [{"symbol": "SOL", "change_pct": 12.345}, {"symbol": "BTC", "change_pct": 3.2}]
    worst = [{"symbol": "DOGE", "change_pct": -7.89}]
    weekly = [
        await report_mailer.send_weekly_report("a@test.com", "Ada", 12345.678, 234.5, 1.94, top, worst),
        await report_mailer.send_weekly_report("a@test.com", "Ada", 9000, -120, -1.3, [], []),
    ]
    rec.check("mail_weekly", {"sent": weekly, "mails": mailbox.drain()})
    allocation = [{"symbol": "BTC", "allocation_pct": 61.5, "value": 7592.1}]
    monthly = [
        await report_mailer.send_monthly_report("a@test.com", "Ada", 12345.6, 300, 2.5, 23.4, allocation),
        await report_mailer.send_monthly_report("a@test.com", "Ada", 9000, -50, -0.5, -10, [], pdf_content=b"%PDF"),
    ]
    rec.check("mail_monthly", {"sent": monthly, "mails": mailbox.drain()})
    alerts = [{"title": "Alerte: BTC > 60k", "message": "Seuil franchi"}]
    digests = [await report_mailer.send_digest("a@test.com", "Ada", alerts)]
    rec.check("mail_digest", {"sent": digests, "mails": mailbox.drain()})


async def test_report_emails_match_golden(mailbox: Mailbox, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder()
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _report_mails(rec, mailbox)
        with monkeypatch.context() as off:
            off.setattr(settings, "SMTP_HOST", "")
            unsent = await report_mailer.send_digest("a@test.com", "Ada", [])
    rec.check("mail_without_smtp", {"sent": unsent, "mails": mailbox.drain()})
    assert not rec.mismatches, f"golden courriels différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


async def _recent(db: AsyncSession, user: User) -> None:
    for title, kind in (("Alerte: BTC au-dessus de 60000", NotificationType.ALERT_TRIGGERED), ("Info", "system")):
        db.add(
            Notification(
                user_id=user.id,
                type=NotificationType(kind),
                title=title,
                message=f"Détail : {title}",
                priority=NotificationPriority.NORMAL,
                created_at=FROZEN_NOW - timedelta(hours=2),
            )
        )
    await db.commit()


@pytest.mark.usefixtures("offline", "live_quotes")
async def test_email_tasks_match_golden(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    mailbox: Mailbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notification_tasks, "session_factory", TestSessionLocal)
    rec = Recorder()
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, {"Authorization": f"Bearer {create_token(str(regular_user.id))}"})
        await _recent(db_session, regular_user)
        results = {
            "weekly": await notification_tasks.run_weekly_reports(),
            "monthly": await notification_tasks.run_monthly_reports(),
            "digest": await notification_tasks.run_daily_digest(),
        }
        rec.check("tasks_sent", {"results": results, "mails": mailbox.drain()})
        with monkeypatch.context() as off:
            off.setattr(settings, "SMTP_HOST", "")
            skipped = {
                "weekly": await notification_tasks.run_weekly_reports(),
                "monthly": await notification_tasks.run_monthly_reports(),
                "digest": await notification_tasks.run_daily_digest(),
            }
    rec.check("tasks_without_smtp", {"results": skipped, "mails": mailbox.drain()})
    assert not rec.mismatches, f"golden tâches courriel différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
