import json
import os
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.core.redis_client import PRICE_UPDATES_CHANNEL, redis_async_url
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.tasks import price_updates
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub

GOLDEN = Path(__file__).parent / "golden" / "price_updates"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
COINGECKO = "api.coingecko.com"
YAHOO = "query1.finance.yahoo.com"
COINS = {
    "bitcoin": ("BTC", {"eur": 50000, "eur_24h_change": 2.0}),
    "solana": ("SOL", {"eur": 150, "eur_24h_change": -1.5}),
}
STOCKS = {"AAPL": 180.0, "SPY": 500.0, "NOPE": None}
JOBS = {"crypto": price_updates._maj_crypto, "stocks": price_updates._maj_actions}

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _coingecko(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/search"):
        query = request.url.params["query"].upper()
        coins = [{"id": coin, "symbol": symbol} for coin, (symbol, _) in COINS.items() if symbol == query]
        return httpx.Response(200, json={"coins": coins}, request=request)
    ids = request.url.params["ids"].split(",")
    return httpx.Response(200, json={coin: COINS[coin][1] for coin in ids if coin in COINS}, request=request)


def _yahoo(request: httpx.Request) -> httpx.Response:
    ticker = request.url.path.rsplit("/", 1)[1]
    meta: dict[str, Any] = {"currency": "EUR", "previousClose": 100.0, "exchangeName": "PAR"}
    if STOCKS.get(ticker) is not None:
        meta["regularMarketPrice"] = STOCKS[ticker]
    return httpx.Response(200, json={"chart": {"result": [{"meta": meta}]}}, request=request)


def _unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, request=request)


async def _portfolio(client: AsyncClient, user: User) -> tuple[dict[str, str], str]:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=headers)).json()["id"]
    return headers, portfolio_id


async def _hold(
    client: AsyncClient, auth: tuple[dict[str, str], str], symbol: str, asset_type: str, sold: bool = False
) -> None:
    headers, portfolio_id = auth
    asset_id = (
        await client.post(
            "/api/v1/assets",
            json={"portfolio_id": portfolio_id, "symbol": symbol, "asset_type": asset_type},
            headers=headers,
        )
    ).json()["id"]
    for kind, moment in (("buy", "2025-01-10T10:00:00Z"), ("sell", "2025-02-10T10:00:00Z"))[: 2 if sold else 1]:
        response = await client.post(
            "/api/v1/transactions",
            json={
                "asset_id": asset_id,
                "transaction_type": kind,
                "quantity": "2",
                "price": "100",
                "currency": "EUR",
                "executed_at": moment,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text


async def _holdings(client: AsyncClient, regular_user: User, admin_user: User) -> None:
    mine = await _portfolio(client, regular_user)
    theirs = await _portfolio(client, admin_user)
    for symbol, asset_type in (("BTC", "crypto"), ("sol", "crypto"), ("ZZZ", "crypto")):
        await _hold(client, mine, symbol, asset_type)
    await _hold(client, mine, "ETH", "crypto", sold=True)
    await _hold(client, theirs, "BTC", "crypto")
    for symbol, asset_type in (("AAPL", "stock"), ("NOPE", "stock"), ("SPY", "etf")):
        await _hold(client, mine, symbol, asset_type)
    await _hold(client, theirs, "MSFT", "stock", sold=True)


def _request(request: httpx.Request) -> str:
    route = f"{request.url.host}{request.url.path}"
    if "ids" in request.url.params:
        return f"{route}?ids={','.join(sorted(request.url.params['ids'].split(',')))}"
    if "query" in request.url.params:
        return f"{route}?query={request.url.params['query']}"
    return route


async def _run(job: Callable[[], Awaitable[dict[str, Any]]], http_stub: HttpStub) -> dict[str, Any]:
    listener = aioredis.from_url(redis_async_url(), decode_responses=True)
    channel = listener.pubsub()
    await channel.subscribe(PRICE_UPDATES_CHANNEL)
    await channel.get_message(timeout=1)
    http_stub.requests.clear()
    result = await job()
    published = []
    while (message := await channel.get_message(ignore_subscribe_messages=True, timeout=0.5)) is not None:
        published.append(json.loads(message["data"]))
    await channel.aclose()
    await listener.aclose()
    return {
        "result": {**result, "symbols": sorted(result["symbols"])},
        "published": sorted(published, key=lambda tick: tick["symbol"]),
        "requests": dict(sorted(Counter(_request(r) for r in http_stub.requests).items())),
    }


def _check(name: str, observed: dict[str, Any]) -> None:
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(observed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1)"


@pytest.fixture
def background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(price_updates, "session_factory", TestSessionLocal)


@pytest.mark.usefixtures("db_session", "background")
@pytest.mark.parametrize("kind", JOBS)
async def test_without_holdings(kind: str, http_stub: HttpStub) -> None:
    _check(f"{kind}_without_holdings", await _run(JOBS[kind], http_stub))


@pytest.mark.usefixtures("background")
@pytest.mark.parametrize("kind", JOBS)
async def test_holdings_are_published(
    kind: str, client: AsyncClient, regular_user: User, admin_user: User, http_stub: HttpStub
) -> None:
    http_stub.on(COINGECKO, _coingecko)
    http_stub.on(YAHOO, _yahoo)
    await _holdings(client, regular_user, admin_user)
    _check(f"{kind}_holdings", await _run(JOBS[kind], http_stub))


@pytest.mark.usefixtures("background")
@pytest.mark.parametrize("kind", JOBS)
async def test_provider_unavailable(
    kind: str, client: AsyncClient, regular_user: User, admin_user: User, http_stub: HttpStub
) -> None:
    http_stub.on(COINGECKO, _unavailable)
    http_stub.on(YAHOO, _unavailable)
    await _holdings(client, regular_user, admin_user)
    _check(f"{kind}_provider_unavailable", await _run(JOBS[kind], http_stub))
