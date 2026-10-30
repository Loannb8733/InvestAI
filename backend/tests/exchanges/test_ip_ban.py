from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_api_key
from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.failures import mark_failure
from app.domains.exchanges.models import FAILURES_BEFORE_DISABLE, APIKey, APIKeyStatus
from app.domains.exchanges.service import ExchangeAccounts
from app.domains.exchanges.sync.runner import sync_account
from app.domains.identity.models import User
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.usefixtures("empty_test_redis")

SIGNED_URL = "https://api.binance.com/api/v3/account?timestamp=1793367323936&signature=e4676a2c3985"


def _ban() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", SIGNED_URL)
    response = httpx.Response(418, request=request)
    message = f"Client error '418 I'm a teapot' for url '{SIGNED_URL}'"
    return httpx.HTTPStatusError(message, request=request, response=response)


class BannedClient:
    exchange_name = "binance"

    async def test_connection(self) -> bool:
        return True

    async def get_balances(self) -> list[ExchangeBalance]:
        raise _ban()


async def _key(db: AsyncSession, user: User) -> APIKey:
    key = APIKey(
        user_id=user.id,
        exchange="binance",
        encrypted_api_key=encrypt_api_key("k"),
        encrypted_secret_key=encrypt_api_key("s"),
        is_active=True,
    )
    db.add(key)
    await db.commit()
    return key


def test_an_ip_ban_never_disables_the_key() -> None:
    key = APIKey(id=uuid4(), error_count=0, is_active=True, status=APIKeyStatus.ACTIVE)
    for _ in range(FAILURES_BEFORE_DISABLE):
        mark_failure(key, _ban())
    assert (key.status, key.is_active) == (APIKeyStatus.RATE_LIMITED, True)


async def test_a_banned_sync_keeps_the_signed_url_out_of_the_error_and_the_logs(
    db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("app.domains.exchanges.sync.runner.session_factory", TestSessionLocal)
    monkeypatch.setattr("app.domains.exchanges.sync.runner.open_client", lambda key: BannedClient())
    key = await _key(db_session, regular_user)
    assert not (await sync_account(key.id)).success
    db_session.expire_all()
    stored = (await db_session.execute(select(APIKey))).scalar_one()
    assert stored.last_error is not None and "418" in stored.last_error
    assert "signature" not in stored.last_error
    assert "signature" not in caplog.text


async def test_a_failed_connection_test_keeps_the_signed_url_out_of_the_error(
    db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.domains.exchanges.service.open_client", lambda key: BannedClient())
    key = await _key(db_session, regular_user)
    result = await ExchangeAccounts(db_session).test_key(regular_user.id, key.id)
    assert result.success is False
    assert key.last_error is not None and "418" in key.last_error and "signature" not in key.last_error
