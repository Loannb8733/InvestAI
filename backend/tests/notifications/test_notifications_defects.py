from datetime import UTC, datetime
from email import message_from_string
from email.header import decode_header, make_header
from email.message import Message
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.identity.emails import send_password_reset_link
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.notifications import mail
from app.domains.notifications import reports as notification_reports
from app.domains.notifications.models import Notification, NotificationPriority, NotificationType
from app.domains.notifications.report_bodies import monthly_email, weekly_email
from app.domains.notifications.report_mailer import report_mailer
from app.domains.notifications.repository import NotificationRepository
from app.domains.notifications.service import NotificationService
from app.domains.notifications.telegram.messages import bottom_zone_text
from tests.notifications.recording import Mailbox
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis")


@pytest.fixture
def outbox(mailbox: Mailbox, monkeypatch: pytest.MonkeyPatch) -> list[Message]:
    sent: list[Message] = []
    monkeypatch.setattr(mail, "_deliver", lambda to_email, raw: sent.append(message_from_string(raw)))
    return sent


def _part(message: Message, content_type: str) -> str:
    part = next(p for p in message.walk() if p.get_content_type() == content_type)
    payload = part.get_payload(decode=True)
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


class _Connections:
    def __init__(self, mailbox: Mailbox) -> None:
        self.mailbox = mailbox
        self.opened: list[tuple[str, dict[str, Any]]] = []

    def factory(self, kind: str) -> Any:
        def open_connection(*args: Any, **kwargs: Any) -> Mailbox:
            self.opened.append((kind, kwargs))
            return self.mailbox

        return open_connection


@pytest.fixture
def connections(mailbox: Mailbox, monkeypatch: pytest.MonkeyPatch) -> _Connections:
    recorded = _Connections(mailbox)
    monkeypatch.setattr("smtplib.SMTP", recorded.factory("starttls"))
    monkeypatch.setattr("smtplib.SMTP_SSL", recorded.factory("ssl"))
    return recorded


async def test_smtp_connection_gives_up_instead_of_hanging(connections: _Connections) -> None:
    assert await mail.send_email("a@test.com", "Ada", "Objet", "Corps")
    assert await report_mailer.send_digest("a@test.com", "Ada", [{"title": "Alerte", "message": "Seuil"}])
    assert [kwargs["timeout"] for _, kwargs in connections.opened] == [mail.SMTP_TIMEOUT_SECONDS] * 2


async def test_notification_email_without_starttls_is_still_encrypted(
    connections: _Connections, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SMTP_TLS", False)
    assert await mail.send_email("a@test.com", "Ada", "Objet", "Corps")
    assert [kind for kind, _ in connections.opened] == ["ssl"]


async def test_notification_and_report_emails_share_one_page(outbox: list[Message]) -> None:
    await mail.send_email("a@test.com", "Ada", "Objet", "Corps")
    await report_mailer.send_digest("a@test.com", "Ada", [{"title": "Alerte", "message": "Seuil"}])
    notice, digest = (_part(message, "text/html") for message in outbox)
    footer = f"Ceci est un message automatique de {settings.APP_NAME}. Ne répondez pas à cet email."
    assert footer in notice and footer in digest
    subjects = [str(make_header(decode_header(message["Subject"]))) for message in outbox]
    assert [subject.startswith(f"[{settings.APP_NAME}] ") for subject in subjects] == [True, True]


async def test_monthly_pdf_is_an_attachment_not_an_alternative(outbox: list[Message]) -> None:
    await report_mailer.send_monthly_report("a@test.com", "Ada", 9000, -50, -0.5, -10, [], pdf_content=b"%PDF")
    message = outbox[0]
    assert message.get_content_type() == "multipart/mixed"
    body, attachment = message.get_payload()
    assert body.get_content_type() == "multipart/alternative"
    assert attachment.get_filename().endswith(".pdf")


async def test_reset_email_text_part_gives_the_link_not_raw_html(outbox: list[Message]) -> None:
    await send_password_reset_link(User(email="a@test.com", first_name="Ada"), "jeton")
    text = _part(outbox[0], "text/plain")
    assert "Réinitialiser mon mot de passe : " in text and "reset-password?token=jeton" in text
    assert "<a " not in text and "<br>" not in text and "<strong>" not in text


async def test_user_text_is_escaped_in_emails(
    db_session: AsyncSession, regular_user: User, outbox: list[Message]
) -> None:
    service = NotificationService(NotificationRepository(db_session))
    await service.send_alert(regular_user.id, "<img src=x>", "Prix <b>franchi</b>", regular_user.id)
    html = _part(outbox[0], "text/html")
    assert "<img src=x>" not in html and "&lt;img src=x&gt;" in html
    assert "<b>franchi</b>" not in html
    _, weekly = weekly_email("<i>Ada</i>", 100, 1, 1, [], [], "EUR")
    assert "<i>Ada</i>" not in weekly and "&lt;i&gt;Ada&lt;/i&gt;" in weekly


async def test_digest_names_each_alert_by_its_title(
    db_session: AsyncSession, regular_user: User, outbox: list[Message]
) -> None:
    db_session.add(
        Notification(
            user_id=regular_user.id,
            type=NotificationType.ALERT_TRIGGERED,
            title="Alerte: BTC au-dessus de 60000",
            message="Seuil franchi",
            priority=NotificationPriority.HIGH,
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    assert await notification_reports.daily_digest(db_session) == {"sent": 1, "failed": 0}
    html = _part(outbox[0], "text/html")
    assert "<strong>Alerte: BTC au-dessus de 60000</strong> : Seuil franchi" in html
    assert "<strong>60000</strong>" not in html


@pytest.mark.usefixtures("offline", "live_quotes")
async def test_weekly_report_ranks_the_assets_of_the_week(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailer = MagicMock(is_configured=True, send_weekly_report=AsyncMock(return_value=True))
    monkeypatch.setattr(notification_reports, "report_mailer", mailer)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, {"Authorization": f"Bearer {create_token(str(regular_user.id))}"})
        assert await notification_reports.weekly_reports(db_session) == {"sent": 1, "failed": 0}
    sent = mailer.send_weekly_report.await_args.kwargs
    ranked = sent["top_performers"] + sent["worst_performers"]
    assert ranked
    assert all(p["change_pct"] > 0 for p in sent["top_performers"])
    assert all(p["change_pct"] < 0 for p in sent["worst_performers"])


def test_amounts_and_percentages_are_written_the_french_way() -> None:
    subject, weekly = weekly_email("Ada", 12345.678, 234.5, 1.94, [{"symbol": "SOL", "change_pct": -7.89}], [], "EUR")
    assert subject == "Rapport hebdomadaire - +1,9\u00a0%"
    assert "12\u00a0345,68\u00a0EUR" in weekly and "+234,50\u00a0EUR" in weekly and "-7,9\u00a0%" in weekly
    assert "12,345.68" not in weekly
    zone = bottom_zone_text("BTC", 58000.5, 55000.0, 0.82, 5.45)
    assert "58\u00a0000,50\u00a0€" in zone and "82\u00a0%" in zone


def test_report_texts_carry_their_accents() -> None:
    _, monthly = monthly_email("Ada", 9000, -50, -0.5, -10, [], "EUR")
    assert "Répartition du portefeuille" in monthly and "Depuis le début de l'année" in monthly
    assert "Aucune donnée" in monthly and "Repartition" not in monthly
