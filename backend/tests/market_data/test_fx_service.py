from datetime import date
from decimal import Decimal

import httpx
import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fx.models import FxDailyRate
from app.domains.market_data.fx.reference import resolve_rate
from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.service import FxQuote, FxService
from app.domains.market_data.fx.spot import spot_rates
from tests.http_stubs import HttpStub

SPOT_HOST = "api.exchangerate-api.com"
ECB_HOST = "api.frankfurter.dev"
TODAY = date(2026, 10, 19)


async def _rates(db: AsyncSession, *rows: tuple[date, str, str, str]) -> None:
    db.add_all([FxDailyRate(rate_date=d, base_currency=b, quote_currency=q, rate=Decimal(r)) for d, b, q, r in rows])
    await db.commit()


def _service(db: AsyncSession) -> FxService:
    return FxService(FxRateRepository(db))


class TestResolveRate:
    SERIES = [(date(2024, 1, 15), Decimal("0.91")), (date(2024, 1, 19), Decimal("0.92"))]

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2024, 1, 15), Decimal("0.91")),
            (date(2024, 1, 17), Decimal("0.91")),
            (date(2024, 1, 20), Decimal("0.92")),
            (date(2024, 1, 14), None),
        ],
    )
    def test_forward_fill_and_no_rate_before_history(self, day: date, expected: Decimal | None) -> None:
        assert resolve_rate(day, self.SERIES) == expected

    def test_empty_history(self) -> None:
        assert resolve_rate(date(2024, 1, 15), []) is None


@pytest.mark.usefixtures("empty_test_redis")
class TestLatest:
    async def test_live_spot_is_fresh(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        http_stub.json(SPOT_HOST, {"rates": {"EUR": 0.8}})
        assert await _service(db_session).latest("USD", "EUR") == FxQuote(Decimal("0.8"), stale=False)

    async def test_falls_back_to_last_ecb_rate_then_inverse(
        self, db_session: AsyncSession, http_stub: HttpStub
    ) -> None:
        await _rates(db_session, (date(2026, 10, 1), "USD", "EUR", "0.8"))
        service = _service(db_session)
        with time_machine.travel(TODAY, tick=False):
            assert await service.latest("USD", "EUR") == FxQuote(Decimal("0.8"), stale=True)
            assert await service.latest("EUR", "USD") == FxQuote(Decimal("1.25"), stale=True)

    async def test_cold_start_when_nothing_is_available(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        assert await _service(db_session).latest("USD", "EUR") == FxQuote(Decimal("0.92"), stale=True)

    async def test_non_fiat_is_never_requested(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        assert await _service(db_session).latest("BTC", "EUR") is None
        assert not http_stub.requests

    async def test_fiat_pair_without_any_source_is_none(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        assert await _service(db_session).latest("JPY", "SEK") is None


class TestRateOn:
    async def test_same_currency_is_one(self, db_session: AsyncSession) -> None:
        assert await _service(db_session).rate_on(TODAY, "eur", "EUR") == Decimal("1")

    async def test_direct_only_unless_inverse_allowed(self, db_session: AsyncSession) -> None:
        await _rates(db_session, (date(2025, 1, 2), "USD", "EUR", "0.8"))
        service = _service(db_session)
        assert await service.rate_on(date(2025, 1, 4), "USD", "EUR") == Decimal("0.8")
        assert await service.rate_on(date(2025, 1, 4), "EUR", "USD") is None
        assert await service.rate_on(date(2025, 1, 4), "EUR", "USD", allow_inverse=True) == Decimal("1.25")
        assert await service.rate_on(date(2025, 1, 1), "USD", "EUR") is None


class TestRefresh:
    async def test_seeds_full_history_then_only_the_tail(self, db_session: AsyncSession, http_stub: HttpStub) -> None:
        def ecb(request: httpx.Request) -> httpx.Response:
            assert request.url.params["base"] == "USD" and request.url.params["symbols"] == "EUR"
            span = request.url.path.rsplit("/", 1)[1]
            rates = {"2026-10-16": {"EUR": 0.85}, "2026-10-19": {"EUR": 0.86}}
            if span.startswith("2026-10-19"):
                rates = {"2026-10-19": {"EUR": 0.86}, "2026-10-20": {"EUR": 0.87}}
            return httpx.Response(200, json={"rates": rates}, request=request)

        http_stub.on(ECB_HOST, ecb)
        service = _service(db_session)
        with time_machine.travel(TODAY, tick=False):
            assert await service.refresh("usd", "eur", date(2026, 10, 1)) == 2
            await db_session.commit()
            assert await service.rate_on(TODAY, "USD", "EUR") == Decimal("0.86")
            assert await service.refresh("USD", "EUR", date(2026, 10, 1)) == 0
        with time_machine.travel(date(2026, 10, 20), tick=False):
            assert await service.refresh("USD", "EUR", date(2026, 10, 1)) == 1
            assert await service.rate_on(date(2026, 10, 20), "USD", "EUR") == Decimal("0.87")
        paths = [r.url.path.rsplit("/", 1)[1] for r in http_stub.requests]
        assert paths == ["2026-10-01..2026-10-19", "2026-10-19..2026-10-20"]


@pytest.mark.usefixtures("empty_test_redis")
class TestSpotRates:
    async def test_cached_in_redis_and_memo(self, http_stub: HttpStub) -> None:
        http_stub.json(SPOT_HOST, {"rates": {"EUR": 0.8}})
        assert await spot_rates.get("usd", "eur") == Decimal("0.8")
        assert await spot_rates.get("USD", "EUR") == Decimal("0.8")
        spot_rates.clear()
        assert await spot_rates.get("USD", "EUR") == Decimal("0.8")
        assert len(http_stub.requests) == 1

    async def test_unreachable_api_gives_none(self, http_stub: HttpStub) -> None:
        assert await spot_rates.get("USD", "EUR") is None
