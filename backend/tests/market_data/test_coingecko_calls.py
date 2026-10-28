from datetime import date, datetime

import httpx
import pytest

from app.core.config import settings
from app.domains.market_data.history.coingecko import CoinGeckoHistory
from app.domains.market_data.prices.service import PriceService
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"


def _coingecko(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/search"):
        return httpx.Response(200, json={"coins": []}, request=request)
    if request.url.path.endswith("/simple/price"):
        return httpx.Response(200, json={"bitcoin": {"eur": 100}}, request=request)
    return httpx.Response(200, json={"prices": [[0, 100.0]], "total_volumes": [[0, 1.0]]}, request=request)


def _paths(http_stub: HttpStub) -> list[str]:
    return [request.url.path.removeprefix("/api/v3") for request in http_stub.requests]


@pytest.mark.usefixtures("empty_test_redis")
async def test_the_demo_key_is_sent_by_both_coingecko_clients(
    http_stub: HttpStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "COINGECKO_API_KEY", "demo-key")
    http_stub.on(COINGECKO, _coingecko)
    await PriceService().crypto(["BTC"])
    history = CoinGeckoHistory()
    await history.daily("BTC", 2)
    await history.close()
    assert [request.headers.get("x-cg-demo-api-key") for request in http_stub.requests] == ["demo-key"] * 2


@pytest.mark.usefixtures("empty_test_redis")
async def test_a_coin_coingecko_does_not_list_is_searched_once_then_never_asked(http_stub: HttpStub) -> None:
    http_stub.on(COINGECKO, _coingecko)
    first = await PriceService().crypto(["BTC", "SOL03"])
    second = await PriceService().crypto(["BTC", "SOL03"])
    past = await PriceService().crypto_on("SOL03", date(2026, 1, 1))
    assert (list(first), list(second), past) == (["BTC"], ["BTC"], None)
    assert _paths(http_stub) == ["/search", "/simple/price"]
    assert http_stub.requests[1].url.params["ids"] == "bitcoin"


@pytest.mark.usefixtures("empty_test_redis")
async def test_history_does_not_ask_coingecko_for_a_coin_it_does_not_list(http_stub: HttpStub) -> None:
    http_stub.on(COINGECKO, _coingecko)
    history = CoinGeckoHistory()
    daily = await history.daily("SOL03", 365)
    between = await history.between("SOL03", datetime(2026, 1, 1), datetime(2026, 2, 1))
    await history.close()
    assert (daily.prices, between.prices, _paths(http_stub)) == ([], [], ["/search"])
