import httpx
import pytest

from app.domains.market_data.prices import cache, coingecko
from app.domains.market_data.prices.service import PriceService
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"


@pytest.fixture
def redis_quota_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exhausted() -> None:
        raise ConnectionError("max requests limit exceeded. Limit: 500000, Usage: 500000")

    monkeypatch.setattr(cache, "_get_redis_txt", exhausted)
    monkeypatch.setattr(coingecko, "_get_redis_txt", exhausted)
    monkeypatch.setattr(cache, "_memory", {})


def _coingecko(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/search"):
        return httpx.Response(200, json={"coins": [{"id": "new-coin", "symbol": "nwc"}]}, request=request)
    return httpx.Response(200, json={"bitcoin": {"eur": 100}, "new-coin": {"eur": 3}}, request=request)


@pytest.mark.usefixtures("redis_quota_exceeded")
async def test_quotes_stay_cached_in_memory_while_redis_is_down(http_stub: HttpStub) -> None:
    http_stub.on(COINGECKO, _coingecko)
    first = await PriceService().crypto(["BTC"])
    second = await PriceService().crypto(["BTC"])
    assert (first["BTC"].price, second["BTC"].price, len(http_stub.requests)) == (100, 100, 1)


@pytest.mark.usefixtures("redis_quota_exceeded")
async def test_an_unknown_symbol_is_still_searched_while_redis_is_down(http_stub: HttpStub) -> None:
    http_stub.on(COINGECKO, _coingecko)
    assert (await PriceService().crypto(["NWC"]))["NWC"].price == 3
