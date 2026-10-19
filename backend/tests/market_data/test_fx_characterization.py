from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.fx_rate import FxDailyRate
from app.models.user import User
from tests.http_stubs import HttpStub

SPOT_HOST = "api.exchangerate-api.com"


async def _portfolio(client: AsyncClient, db: AsyncSession, user: User, currency: str) -> tuple[dict[str, str], str]:
    user.preferred_currency = currency
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "FX"}, headers=headers)).json()["id"]
    asset_id = (
        await client.post(
            "/api/v1/assets",
            json={"portfolio_id": portfolio_id, "symbol": "FXCOIN", "asset_type": "crypto"},
            headers=headers,
        )
    ).json()["id"]
    await client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "transaction_type": "buy",
            "quantity": "2",
            "price": "100",
            "currency": "EUR",
            "executed_at": "2025-01-10T10:00:00Z",
        },
        headers=headers,
    )
    return headers, portfolio_id


async def _stale_flags(client: AsyncClient, headers: dict[str, str], portfolio_id: str) -> tuple[bool, bool]:
    portfolio = (await client.get(f"/api/v1/dashboard/portfolio/{portfolio_id}", headers=headers)).json()
    dashboard = (await client.get("/api/v1/dashboard", headers=headers)).json()
    return portfolio["forex_stale"], dashboard["forex_stale"]


@pytest.mark.usefixtures("empty_test_redis")
@pytest.mark.parametrize("currency", ["EUR", "USD"])
async def test_without_any_rate_conversions_are_flagged_stale(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub, currency: str
) -> None:
    headers, portfolio_id = await _portfolio(client, db_session, regular_user, currency)
    assert await _stale_flags(client, headers, portfolio_id) == (True, True)


@pytest.mark.usefixtures("empty_test_redis")
async def test_persisted_ecb_rate_alone_is_still_flagged_stale(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
) -> None:
    db_session.add(
        FxDailyRate(rate_date=date(2026, 10, 1), base_currency="USD", quote_currency="EUR", rate=Decimal("0.8"))
    )
    await db_session.commit()
    headers, portfolio_id = await _portfolio(client, db_session, regular_user, "USD")
    assert await _stale_flags(client, headers, portfolio_id) == (True, True)


@pytest.mark.usefixtures("empty_test_redis")
@pytest.mark.parametrize("currency", ["EUR", "USD"])
async def test_live_spot_rates_are_not_stale(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub, currency: str
) -> None:
    http_stub.json(SPOT_HOST, {"rates": {"USD": 1.25, "EUR": 0.8, "GBP": 0.7, "CHF": 0.9}})
    headers, portfolio_id = await _portfolio(client, db_session, regular_user, currency)
    assert await _stale_flags(client, headers, portfolio_id) == (False, False)
