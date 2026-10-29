import pytest

from app.api.v1.endpoints import telegram_webhook
from app.core.config import settings
from app.services import telegram_service
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub
from tests.notifications.recording import Mailbox, Telegram

TELEGRAM_SECRET = "secret-de-caracterisation"


@pytest.fixture
def telegram(http_stub: HttpStub, monkeypatch: pytest.MonkeyPatch) -> Telegram:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "jeton-de-test")
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", TELEGRAM_SECRET)
    monkeypatch.setattr(telegram_service, "_redis", None)
    monkeypatch.setattr(telegram_service.TelegramService, "_client", None)
    monkeypatch.setattr(telegram_webhook, "session_factory", TestSessionLocal)
    return Telegram(http_stub)


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> Mailbox:
    box = Mailbox()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_USER", "investai")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "mot-de-passe")
    monkeypatch.setattr("smtplib.SMTP", box.smtp)
    monkeypatch.setattr("smtplib.SMTP_SSL", box.smtp)
    return box
