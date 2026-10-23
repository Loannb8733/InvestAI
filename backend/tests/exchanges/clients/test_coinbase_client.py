from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

import app.domains.exchanges.connectors.coinbase.movements as movements_module
import app.domains.exchanges.connectors.coinbase.trades as trades_module
from app.domains.exchanges.connectors.coinbase.connector import CoinbaseService
from tests.exchanges.clients.harness import assert_golden, install, record

ACCOUNTS = "/api/v3/brokerage/accounts"
FILLS = "/api/v3/brokerage/orders/historical/fills"
SINCE = datetime(2026, 1, 1, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, tzinfo=UTC)


def _account(uuid: str, currency: str, available: str, hold: str | None = None) -> dict[str, Any]:
    account: dict[str, Any] = {"uuid": uuid, "currency": currency, "available_balance": {"value": available}}
    if hold is not None:
        account["hold"] = {"value": hold}
    return account


def _fill(key: str, product: str, side: str, when: str, id_field: str = "trade_id") -> dict[str, Any]:
    return {
        id_field: key,
        "product_id": product,
        "side": side,
        "size": "0.01",
        "price": "60000.5",
        "commission": "0.6",
        "trade_time": when,
    }


def _tx(key: str, amount: dict[str, str], **fields: Any) -> dict[str, Any]:
    return {"id": key, "amount": amount, **fields}


def _by_cursor(pages: dict[str, Any]) -> Callable[[httpx.Request], Any]:
    return lambda request: pages[request.url.params.get("cursor", "")]


def _by_type(**pages: Any) -> Callable[[httpx.Request], Any]:
    return lambda request: pages[request.url.params["type"]]


ACCOUNT_PAGES = {
    "": {
        "accounts": [
            _account("a-btc", "BTC", "0.5", "0.1"),
            _account("a-eth", "ETH", "2"),
            _account("a-doge", "DOGE", "0", "0"),
        ],
        "has_next": True,
        "cursor": "p2",
    },
    "p2": {"accounts": [_account("a-usd", "USD", "100.25", "0")], "has_next": False, "cursor": "p3"},
}

FILL_PAGES = {
    "": {
        "fills": [
            _fill("t1", "BTC-USD", "BUY", "2026-09-01T10:00:00Z"),
            _fill("e2", "BTCUSD", "sell", "2026-09-02T10:00:00.250Z", id_field="entry_id"),
        ],
        "cursor": "f2",
    },
    "f2": {"fills": [_fill("t3", "ETH-EUR", "Sell", "2026-08-01T00:00:00+00:00")], "cursor": ""},
}

BTC_DEPOSITS = {
    "transactions": [
        _tx(
            "d1",
            {"value": "-0.25", "currency": "BTC"},
            created_at="2026-09-10T08:00:00Z",
            status="completed",
            network={"hash": "0xabc"},
        ),
        _tx("d2", {"value": "1"}, created_at="2025-01-01T00:00:00Z"),
        _tx("d3", {"amount": "0.1"}, payout_at="2026-09-11T00:00:00Z"),
    ]
}

BTC_WITHDRAWALS = {
    "transactions": [
        _tx(
            "w1",
            {"value": "-0.05", "currency": "BTC"},
            fee={"value": "-0.0001"},
            created_at="2026-09-12T00:00:00Z",
            status="completed",
            network={"hash": "txw1", "to_address_info": {"address": "bc1qxyz"}},
        ),
        _tx("w2", {"value": "-1"}, created_at="2025-06-01T00:00:00Z"),
    ]
}


async def test_coinbase_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, trades_module, movements_module)
    client = CoinbaseService("key", "secret")
    api.on("GET", ACCOUNTS, _by_cursor(ACCOUNT_PAGES))
    api.on("GET", FILLS, _by_cursor(FILL_PAGES))
    api.on("GET", f"{ACCOUNTS}/a-btc/transactions", _by_type(deposit=BTC_DEPOSITS, withdrawal=BTC_WITHDRAWALS))
    api.on("GET", f"{ACCOUNTS}/a-usd/transactions", _by_type(deposit={"transactions": []}, withdrawal={}))
    api.on(
        "GET",
        "/v2/accounts/a-eth/deposits",
        {
            "data": [
                _tx("d4", {"amount": "1.5", "currency": "ETH"}, status="pending"),
            ]
        },
    )
    api.on(
        "GET",
        "/v2/accounts/a-eth/withdrawals",
        {
            "data": [
                _tx(
                    "w3",
                    {"amount": "0.5"},
                    fee={"amount": "0.001"},
                    payout_at="2026-09-20T00:00:00Z",
                    network={"hash": "0xw3"},
                ),
            ]
        },
    )
    observed = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "connection_error": await record(api, client.connection_error),
        "balances": await record(api, client.get_balances),
        "accounts": await record(api, client._get_account_ids),
        "accounts_eth": await record(api, lambda: client._get_account_ids("ETH")),
        "trades": await record(
            api, lambda: client.get_trades(symbol="BTC-USD", start_time=SINCE, end_time=UNTIL, limit=150)
        ),
        "trades_limited": await record(api, lambda: client.get_trades(limit=2)),
        "deposits": await record(api, lambda: client.get_deposits(start_time=SINCE)),
        "deposits_limited": await record(api, lambda: client.get_deposits(limit=2)),
        "deposits_eth": await record(api, lambda: client.get_deposits(symbol="ETH")),
        "withdrawals": await record(api, lambda: client.get_withdrawals(start_time=SINCE)),
        "withdrawals_limited": await record(api, lambda: client.get_withdrawals(limit=1)),
        "withdrawals_eth": await record(api, lambda: client.get_withdrawals(symbol="ETH")),
        "fiat_orders": await record(api, client.get_fiat_orders),
    }
    api.scripts.clear()
    api.on("GET", ACCOUNTS, {"error": "unauthorized"}, status=401)
    api.on("GET", FILLS, {"error": "boom"}, status=500)
    api.on("GET", FILLS, {"fills": []})
    api.on(
        "GET",
        FILLS,
        {
            "fills": [
                _fill("t4", "BTC-USD", "buy", "2026-09-03T00:00:00Z"),
                {"trade_id": "t5", "product_id": "BTC-USD"},
            ]
        },
    )
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["accounts_refused"] = await record(api, client._get_account_ids)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)
    observed["trades_http_error"] = await record(api, client.get_trades)
    observed["trades_empty"] = await record(api, client.get_trades)
    observed["trades_malformed"] = await record(api, client.get_trades)
    api.scripts.clear()
    api.on("GET", ACCOUNTS, {})
    observed["balances_empty"] = await record(api, client.get_balances)
    observed["accounts_empty"] = await record(api, client._get_account_ids)
    keyless = CoinbaseService("key")
    observed["connection_without_secret"] = await record(api, keyless.test_connection)
    observed["balances_without_secret"] = await record(api, keyless.get_balances)
    assert_golden("coinbase", observed)
