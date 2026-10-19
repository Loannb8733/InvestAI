from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User
from tests.http_stubs import HttpStub

COINGECKO = "api.coingecko.com"
YAHOO = "query1.finance.yahoo.com"
SPOT = "api.exchangerate-api.com"

pytestmark = pytest.mark.usefixtures("empty_test_redis")


async def _holding(client: AsyncClient, user: User, symbol: str, asset_type: str) -> tuple[dict[str, str], str]:
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=headers)).json()["id"]
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


async def _asset(client: AsyncClient, headers: dict[str, str], portfolio_id: str) -> dict[str, Any]:
    body = (await client.get(f"/api/v1/dashboard/portfolio/{portfolio_id}", headers=headers)).json()
    [asset] = body["assets"]
    return {k: asset[k] for k in ("current_price", "current_value", "change_percent_24h")}


def _yahoo(price: float | None, currency: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"currency": currency, "previousClose": 100.0, "exchangeName": "NMS"}
    if price is not None:
        meta["regularMarketPrice"] = price
    return {"chart": {"result": [{"meta": meta}]}}


async def test_crypto_priced_by_coingecko(client: AsyncClient, regular_user: User, http_stub: HttpStub) -> None:
    http_stub.json(COINGECKO, {"bitcoin": {"eur": 50000, "eur_24h_change": 2.0}})
    headers, pid = await _holding(client, regular_user, "BTC", "crypto")
    assert await _asset(client, headers, pid) == {
        "current_price": 50000.0,
        "current_value": 100000.0,
        "change_percent_24h": 2.0,
    }


async def test_crypto_unpriced_keeps_cost(client: AsyncClient, regular_user: User, http_stub: HttpStub) -> None:
    headers, pid = await _holding(client, regular_user, "BTC", "crypto")
    assert await _asset(client, headers, pid) == {
        "current_price": None,
        "current_value": 200.0,
        "change_percent_24h": 0.0,
    }


async def test_usd_stock_is_converted(client: AsyncClient, regular_user: User, http_stub: HttpStub) -> None:
    http_stub.json(YAHOO, _yahoo(150.0, "USD"))
    http_stub.json(SPOT, {"rates": {"EUR": 0.8, "USD": 1.25}})
    headers, pid = await _holding(client, regular_user, "AAPL", "stock")
    assert await _asset(client, headers, pid) == {
        "current_price": 120.0,
        "current_value": 240.0,
        "change_percent_24h": 50.0,
    }


async def test_stock_without_market_price(client: AsyncClient, regular_user: User, http_stub: HttpStub) -> None:
    http_stub.json(YAHOO, _yahoo(None, "EUR"))
    headers, pid = await _holding(client, regular_user, "MC.PA", "stock")
    assert await _asset(client, headers, pid) == {
        "current_price": None,
        "current_value": 200.0,
        "change_percent_24h": 0.0,
    }


async def test_coingecko_error_without_cryptocompare_key(
    client: AsyncClient, regular_user: User, http_stub: HttpStub
) -> None:
    http_stub.on(COINGECKO, lambda request: httpx.Response(503, request=request))
    headers, pid = await _holding(client, regular_user, "ETH", "crypto")
    assert await _asset(client, headers, pid) == {
        "current_price": None,
        "current_value": 200.0,
        "change_percent_24h": 0.0,
    }
    assert all(
        r.url.host == COINGECKO
        for r in http_stub.requests
        if "coingecko" in str(r.url) or "cryptocompare" in str(r.url)
    )


@pytest.mark.parametrize(("coingecko", "unit_price"), [({"usd-coin": {"eur": 0.79}}, 0.79), (None, 0.8)])
async def test_usd_stablecoin_live_then_spot_rate(
    client: AsyncClient, regular_user: User, http_stub: HttpStub, coingecko: dict[str, Any] | None, unit_price: float
) -> None:
    http_stub.json(SPOT, {"rates": {"EUR": 0.8, "USD": 1.25}})
    if coingecko is not None:
        http_stub.json(COINGECKO, coingecko)
    headers, pid = await _holding(client, regular_user, "USDC", "crypto")
    body = (await client.get(f"/api/v1/dashboard/portfolio/{pid}", headers=headers)).json()
    [stablecoin] = body["stablecoins"]
    assert (stablecoin["unit_price"], stablecoin["value"]) == (unit_price, 2 * unit_price)
