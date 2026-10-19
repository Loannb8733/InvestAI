from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.domains.market_data.fx.models import FxDailyRate
from app.domains.market_data.history import coingecko, reader, service, tasks
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.market_data.history.reader import local_history
from app.domains.market_data.history.repository import HistoryRepository
from app.domains.market_data.history.series import PriceSeries
from app.domains.market_data.prices.service import price_feed
from app.models.asset import Asset
from app.models.user import User
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"
YAHOO = "query1.finance.yahoo.com"


def _day(n: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _yahoo(currency: str, *closes: float | None) -> dict[str, Any]:
    n = len(closes)
    stamps = [int(_day(n - 1 - i).replace(tzinfo=UTC).timestamp()) for i in range(n)]
    quote = {"close": list(closes), "volume": [100] * n}
    return {
        "chart": {"result": [{"meta": {"currency": currency}, "timestamp": stamps, "indicators": {"quote": [quote]}}]}
    }


async def _stored(db: AsyncSession, symbol: str) -> list[tuple[float, str]]:
    rows = await db.execute(
        select(AssetPriceHistory.price_eur, AssetPriceHistory.source)
        .where(AssetPriceHistory.symbol == symbol)
        .order_by(AssetPriceHistory.price_date)
    )
    return [(float(price), source) for price, source in rows.all()]


@pytest.fixture(autouse=True)
def background(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []

    async def no_sleep(seconds: float) -> None:
        waits.append(seconds)

    for module in (tasks, reader):
        monkeypatch.setattr(module, "session_factory", TestSessionLocal)
    for module in (tasks, service, coingecko):
        monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    return waits


async def _holding(client: AsyncClient, user: User, symbol: str, asset_type: str) -> None:
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
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
            "quantity": "1",
            "price": "100",
            "currency": "EUR",
            "executed_at": _day(3).isoformat() + "Z",
        },
        headers=headers,
    )


class TestLocalHistory:
    async def test_reads_the_requested_window_with_volumes(self, db_session: AsyncSession) -> None:
        repository = HistoryRepository(db_session)
        await repository.upsert("BTC", PriceSeries([_day(40), _day(1), _day(0)], [1.0, 2.0, 3.0], [9.0, 8.0, 7.0]), "x")
        await db_session.commit()
        found = await local_history(["btc", "nope"], 30, db_session)
        assert found["BTC"].prices == [2.0, 3.0]
        assert found["BTC"].volumes == [8.0, 7.0]
        assert found["NOPE"] == PriceSeries()

    async def test_never_touches_the_network(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        await local_history(["BTC", "SPY"], 365)
        assert not http_stub.requests


class TestRefresh:
    async def test_crypto_falls_back_to_the_yahoo_euro_pair(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
    ) -> None:
        await _holding(client, regular_user, "BTC", "crypto")
        http_stub.on(COINGECKO, lambda request: httpx.Response(503, request=request))
        http_stub.json(YAHOO, _yahoo("EUR", 50000.0, 51000.0))
        assert await tasks.refresh_symbol("BTC", "crypto") is True
        assert await _stored(db_session, "BTC") == [(50000.0, "yahoo"), (51000.0, "yahoo")]
        assert http_stub.requests[-1].url.path.endswith("/BTC-EUR")
        btc = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
        await db_session.refresh(btc)
        assert float(btc.current_price) == 51000.0

    async def test_stock_closes_are_converted_to_euros(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        db_session.add(
            FxDailyRate(rate_date=date(2020, 1, 1), base_currency="USD", quote_currency="EUR", rate=Decimal("0.8"))
        )
        await db_session.commit()
        http_stub.json(YAHOO, _yahoo("USD", 10.0, None, 20.0))
        assert await tasks.refresh_symbol("SPY", "etf") is True
        assert await _stored(db_session, "SPY") == [(8.0, "yahoo"), (16.0, "yahoo")]

    async def test_nothing_is_stored_without_an_exchange_rate(
        self, db_session: AsyncSession, http_stub: HttpStub
    ) -> None:
        http_stub.json(YAHOO, _yahoo("JPY", 1000.0, 1100.0))
        assert await tasks.refresh_symbol("7203.T", "stock") is False
        assert await _stored(db_session, "7203.T") == []

    async def test_coingecko_429_waits_for_retry_after(
        self, db_session: AsyncSession, http_stub: HttpStub, background: list[float]
    ) -> None:
        answers = iter([429, 200])

        def coingecko_once_refused(request: httpx.Request) -> httpx.Response:
            if next(answers) == 429:
                return httpx.Response(429, headers={"Retry-After": "5"}, request=request)
            return httpx.Response(
                200, json={"prices": [[_day(0).replace(tzinfo=UTC).timestamp() * 1000, 3.0]]}, request=request
            )

        http_stub.on(COINGECKO, coingecko_once_refused)
        assert await tasks.refresh_symbol("ETH", "crypto") is True
        assert 5.0 in background
        assert await _stored(db_session, "ETH") == [(3.0, "coingecko")]


class TestRefreshAll:
    async def test_skips_symbols_up_to_date_and_adds_market_references(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
    ) -> None:
        await _holding(client, regular_user, "BTC", "crypto")
        await _holding(client, regular_user, "FLAT", "real_estate")
        await HistoryRepository(db_session).upsert("BTC", PriceSeries([_day(0)], [1.0]), "coingecko")
        await db_session.commit()
        await tasks.refresh_all()
        asked = {r.url.path.rsplit("/", 1)[-1] for r in http_stub.requests if r.url.host == YAHOO}
        assert {"SPY", "IWDA.AS", "^GSPC", "^IXIC"} <= asked
        coins = {r.url.path for r in http_stub.requests if r.url.host == COINGECKO}
        assert not any("/bitcoin/" in path for path in coins)
        assert not any("FLAT" in r.url.path for r in http_stub.requests)


class TestBackfill:
    async def test_fills_the_days_missing_after_the_first_trade(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User, http_stub: HttpStub
    ) -> None:
        await _holding(client, regular_user, "SOL", "crypto")
        http_stub.json(COINGECKO, {"prices": [[_day(3).replace(tzinfo=UTC).timestamp() * 1000, 10.0]]})
        with patch.object(price_feed, "crypto_on", AsyncMock(return_value=Decimal(12))):
            assert await tasks.backfill_all() == 1
        prices = [price for price, _ in await _stored(db_session, "SOL")]
        assert prices == [10.0, 12.0, 12.0, 12.0]


class TestScheduleRefresh:
    @pytest.fixture(autouse=True)
    def fresh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tasks, "_running", {})
        monkeypatch.setattr(tasks, "_last_attempt", {})

    def test_unquoted_types_are_ignored(self) -> None:
        assert tasks.schedule_refresh("FLAT", "real_estate") == "ignore"

    def test_queued_when_a_worker_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", True)
        with patch.object(tasks.refresh_one, "delay") as delay:
            assert tasks.schedule_refresh("BTC", "crypto") == "file"
        delay.assert_called_once_with("BTC", "crypto")

    async def test_runs_on_the_loop_once_per_hour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)
        refresh = AsyncMock(return_value=True)
        monkeypatch.setattr(tasks, "refresh_symbol", refresh)
        assert tasks.schedule_refresh("btc", "crypto") == "boucle"
        assert tasks.schedule_refresh("BTC", "crypto") == "deja"
        await tasks._running["BTC"]
        refresh.assert_awaited_once_with("BTC", "crypto")

    def test_outside_any_loop_nothing_breaks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)
        assert tasks.schedule_refresh("BTC", "crypto") == "ignore"
