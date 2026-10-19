from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import PriceService
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"
CRYPTOCOMPARE = "min-api.cryptocompare.com"
YAHOO = "query1.finance.yahoo.com"
SPOT = "api.exchangerate-api.com"

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _down(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, request=request)


def _chart(price: float, currency: str, previous: float) -> dict[str, Any]:
    meta = {"regularMarketPrice": price, "previousClose": previous, "currency": currency}
    return {"chart": {"result": [{"meta": meta}]}}


class TestCrypto:
    async def test_quote_is_cached_per_currency(self, http_stub: HttpStub) -> None:
        def coingecko(request: httpx.Request) -> httpx.Response:
            ccy = request.url.params["vs_currencies"]
            body = {"bitcoin": {ccy: 100 if ccy == "eur" else 120, f"{ccy}_24h_change": 10}}
            return httpx.Response(200, json=body, request=request)

        http_stub.on(COINGECKO, coingecko)
        feed = PriceService()
        assert await feed.crypto(["btc"]) == {"BTC": PriceQuote(Decimal(100), 10.0, 10.0)}
        assert (await PriceService().crypto(["BTC"]))["BTC"].price == 100
        assert (await feed.crypto(["BTC"], "usd"))["BTC"].price == 120
        assert len(http_stub.requests) == 2

    async def test_cryptocompare_when_coingecko_fails_and_a_key_exists(
        self, http_stub: HttpStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "CRYPTOCOMPARE_API_KEY", "key")
        http_stub.on(COINGECKO, _down)
        http_stub.json(CRYPTOCOMPARE, {"RAW": {"ETH": {"EUR": {"PRICE": 2000, "CHANGEPCT24HOUR": -1}}}})
        quote = (await PriceService().crypto(["ETH"]))["ETH"]
        assert (quote.price, quote.change_percent_24h) == (Decimal(2000), -1.0)

    async def test_stablecoin_falls_back_to_its_peg_without_cryptocompare_key(self, http_stub: HttpStub) -> None:
        http_stub.on(COINGECKO, _down)
        http_stub.json(SPOT, {"rates": {"EUR": 0.8}})
        assert await PriceService().quote("USDC", "crypto") == PriceQuote(Decimal("0.8"))
        assert all(r.url.host != CRYPTOCOMPARE for r in http_stub.requests)

    async def test_unknown_or_zero_price_is_absent(self, http_stub: HttpStub) -> None:
        http_stub.json(COINGECKO, {"bitcoin": {"eur": 0}, "coins": []})
        assert await PriceService().crypto(["BTC", "NOPE"]) == {}

    async def test_searched_coin_id_is_kept(self, http_stub: HttpStub) -> None:
        def coingecko(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json={"coins": [{"id": "new-coin", "symbol": "nwc"}]}, request=request)
            return httpx.Response(200, json={"new-coin": {"eur": 3}}, request=request)

        http_stub.on(COINGECKO, coingecko)
        assert (await PriceService().crypto(["NWC"]))["NWC"].price == 3
        assert await PriceService()._coingecko.coin_id("NWC") == "new-coin"
        assert sum(r.url.path.endswith("/search") for r in http_stub.requests) == 1

    async def test_price_on_a_past_day_is_cached(self, http_stub: HttpStub) -> None:
        http_stub.json(COINGECKO, {"market_data": {"current_price": {"eur": 42000.5}}})
        day = date(2024, 3, 1)
        assert await PriceService().crypto_on("btc", day) == Decimal("42000.5")
        assert await PriceService().crypto_on("BTC", day) == Decimal("42000.5")
        assert [r.url.params["date"] for r in http_stub.requests] == ["01-03-2024"]


class TestStocks:
    async def test_converted_from_the_quote_currency(self, http_stub: HttpStub) -> None:
        http_stub.json(YAHOO, _chart(150.0, "USD", 100.0))
        http_stub.json(SPOT, {"rates": {"EUR": 0.8}})
        assert (await PriceService().stocks(["aapl"]))["AAPL"] == PriceQuote(Decimal("120.0"), 50.0, 40.0)

    async def test_pence_are_converted_to_pounds(self, http_stub: HttpStub) -> None:
        http_stub.json(YAHOO, _chart(250.0, "GBp", 250.0))
        http_stub.json(SPOT, {"rates": {"EUR": 1.2}})
        assert (await PriceService().quote("HSBA.L", "stock")) == PriceQuote(Decimal("3.0"))

    async def test_absent_without_exchange_rate(self, http_stub: HttpStub) -> None:
        http_stub.json(YAHOO, _chart(150.0, "USD", 100.0))
        assert await PriceService().stocks(["AAPL"]) == {}

    async def test_index_level_is_not_converted(self, http_stub: HttpStub) -> None:
        http_stub.json(YAHOO, _chart(18.5, "USD", 18.0))
        assert await PriceService().index_level("^VIX") == 18.5
        assert all(r.url.host == YAHOO for r in http_stub.requests)


async def test_unquoted_asset_types_have_no_price(http_stub: HttpStub) -> None:
    assert await PriceService().quote("FLAT", "real_estate") is None
    assert not http_stub.requests
