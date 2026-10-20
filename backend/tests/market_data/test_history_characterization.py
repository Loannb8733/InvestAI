from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.fx.models import FxDailyRate
from app.domains.market_data.history import tasks
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.market_data.history.repository import HistoryRepository
from app.domains.market_data.history.series import PriceSeries
from app.models.asset import Asset
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"
YAHOO = "query1.finance.yahoo.com"

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _days_ago(n: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)


def _market_chart(*prices: float) -> dict[str, Any]:
    n = len(prices)
    return {"prices": [[_days_ago(n - 1 - i).timestamp() * 1000, p] for i, p in enumerate(prices)]}


def _yahoo_chart(*closes: float | None) -> dict[str, Any]:
    n = len(closes)
    stamps = [int(_days_ago(n - 1 - i).timestamp()) for i in range(n)]
    return {"chart": {"result": [{"timestamp": stamps, "indicators": {"quote": [{"close": list(closes)}]}}]}}


async def _holding(client: AsyncClient, user: User, symbol: str, asset_type: str) -> tuple[dict[str, str], str]:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "H"}, headers=headers)).json()["id"]
    asset_id = (
        await client.post(
            "/api/v1/assets",
            json={"portfolio_id": portfolio_id, "symbol": symbol, "asset_type": asset_type},
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


@pytest.fixture
def background(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(tasks, "session_factory", TestSessionLocal)
    monkeypatch.setattr(tasks.asyncio, "sleep", no_sleep)


async def _stored(db: AsyncSession, symbol: str) -> list[float]:
    rows = await db.execute(
        select(AssetPriceHistory.price_eur)
        .where(AssetPriceHistory.symbol == symbol)
        .order_by(AssetPriceHistory.price_date)
    )
    return [float(p) for p in rows.scalars()]


@pytest.mark.usefixtures("background")
async def test_refresh_task_persists_history_and_mirrors_current_price(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
) -> None:
    db_session.add(
        FxDailyRate(rate_date=date(2020, 1, 1), base_currency="USD", quote_currency="EUR", rate=Decimal("0.5"))
    )
    await db_session.commit()
    http_stub.json(COINGECKO, _market_chart(100.0, 110.0, 120.0))
    http_stub.json(YAHOO, _yahoo_chart(10.0, None, 12.0))
    await _holding(client, regular_user, "BTC", "crypto")
    await _holding(client, regular_user, "SPY", "etf")

    assert await tasks.refresh_all() == 6
    assert await _stored(db_session, "BTC") == [100.0, 110.0, 120.0]
    assert await _stored(db_session, "SPY") == [5.0, 6.0]
    btc = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
    await db_session.refresh(btc)
    assert float(btc.current_price) == 120.0

    calls = len(http_stub.requests)
    assert await tasks.refresh_all() == 6
    assert len(http_stub.requests) == calls


@pytest.mark.usefixtures("background")
async def test_sparklines_read_the_persisted_history(
    client: AsyncClient, regular_user: User, http_stub: HttpStub
) -> None:
    http_stub.json(COINGECKO, _market_chart(100.0, 150.0, 200.0))
    headers, portfolio_id = await _holding(client, regular_user, "ETH", "crypto")
    await tasks.refresh_symbol("ETH", "crypto")
    http_stub.routes.clear()

    response = await client.get(f"/api/v1/dashboard/portfolio/{portfolio_id}/sparklines", headers=headers)
    assert response.json() == [{"symbol": "ETH", "prices": [0.0, 0.5, 1.0], "change_pct": 100.0}]


async def test_benchmarks_are_read_from_the_stored_history(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
) -> None:
    repository = HistoryRepository(db_session)
    await repository.upsert("BTC", PriceSeries([_days_ago(1), _days_ago(0)], [100.0, 200.0]), "coingecko")
    await repository.upsert("SPY", PriceSeries([_days_ago(1), _days_ago(0)], [50.0, 55.0]), "yahoo")
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    body = (await client.get("/api/v1/dashboard/benchmarks?days=2", headers=headers)).json()
    assert [(s["symbol"], [p["value"] for p in s["data"]]) for s in body] == [
        ("BTC", [100.0, 200.0]),
        ("SPY", [100.0, 110.0]),
    ]
    assert not http_stub.requests
