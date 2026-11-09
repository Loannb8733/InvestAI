from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.alerts import regime
from app.domains.identity.models import User
from app.domains.notifications.telegram import client as telegram
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub

TELEGRAM = "api.telegram.org"

pytestmark = pytest.mark.usefixtures("empty_test_redis")


@pytest.fixture
def remembered(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    remember = AsyncMock()
    monkeypatch.setattr(regime, "session_factory", TestSessionLocal)
    monkeypatch.setattr(regime, "current_regime", AsyncMock(return_value="bullish"))
    monkeypatch.setattr(regime, "last_regime", AsyncMock(return_value="bearish"))
    monkeypatch.setattr(regime, "remember_regime", remember)
    return remember


async def _recipient(db: AsyncSession) -> None:
    db.add(User(email="actif@test.com", password_hash="x", telegram_enabled=True, telegram_chat_id="111"))
    await db.commit()


async def test_an_undelivered_alert_is_not_counted_nor_forgotten(
    db_session: AsyncSession, remembered: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _recipient(db_session)
    monkeypatch.setattr(regime.telegram_service, "send_smart_alert", AsyncMock(return_value=None))
    result = await regime.check_regime_mutation()
    assert result["users_notified"] == 0
    remembered.assert_not_awaited()


@pytest.mark.usefixtures("db_session")
async def test_without_recipient_the_new_regime_is_remembered(remembered: AsyncMock) -> None:
    result = await regime.check_regime_mutation()
    assert result["users_notified"] == 0
    remembered.assert_awaited_once_with("bullish")


async def test_a_reversal_within_four_hours_is_announced(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, http_stub: HttpStub
) -> None:
    monkeypatch.setattr(regime, "session_factory", TestSessionLocal)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "jeton")
    monkeypatch.setattr(telegram, "_redis", None)
    monkeypatch.setattr(telegram.TelegramService, "_client", None)
    http_stub.on(TELEGRAM, lambda r: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}, request=r))
    await _recipient(db_session)
    for old, new in (("bearish", "bullish"), ("bullish", "bearish")):
        monkeypatch.setattr(regime, "current_regime", AsyncMock(return_value=new))
        monkeypatch.setattr(regime, "last_regime", AsyncMock(return_value=old))
        assert (await regime.check_regime_mutation())["users_notified"] == 1
    assert len([r for r in http_stub.requests if r.url.host == TELEGRAM]) == 2
