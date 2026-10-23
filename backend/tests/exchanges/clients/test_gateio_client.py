from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

import app.services.exchanges.gateio as module
from app.services.exchanges.gateio import GateIOService
from tests.exchanges.clients.harness import assert_golden, install, record

ACCOUNTS = "/api/v4/spot/accounts"
MY_TRADES = "/api/v4/spot/my_trades"
DEPOSITS = "/api/v4/wallet/deposits"
WITHDRAWALS = "/api/v4/wallet/withdrawals"
REFUSED = {"label": "INVALID_KEY", "message": "Invalid key provided"}
SINCE = datetime(2026, 1, 1, tzinfo=UTC)
UNTIL = datetime(2026, 9, 1, tzinfo=UTC)
ACCOUNT_ROWS = [
    {"currency": "BTC", "available": "0.4", "locked": "0.1"},
    {"currency": "USDT", "available": "250", "locked": "0"},
    {"currency": "ETH", "available": 1.25, "locked": "0"},
    {"currency": "EUR", "available": "10", "locked": "0"},
    {"currency": "DUST", "available": "0", "locked": "0"},
]
DEPOSIT_STATUSES = ["DONE", "CANCEL", "REQUEST", "MANUAL", "BCODE", "OTHER"]
WITHDRAWAL_STATUSES = [
    "DONE",
    "CANCEL",
    "REQUEST",
    "MANUAL",
    "BCODE",
    "EXTPEND",
    "FAIL",
    "INVALID",
    "VERIFY",
    "PROCES",
    "PEND",
    "DMOVE",
    "OTHER",
]


def _trade(trade_id: int, side: str, create_time: str, pair: str | None = None) -> dict[str, Any]:
    row = {
        "id": trade_id,
        "side": side,
        "amount": "0.01",
        "price": "60000.5",
        "fee": "0.6",
        "fee_currency": "USDT",
        "create_time": create_time,
    }
    return row if pair is None else {**row, "currency_pair": pair}


BOOK = {
    "BTC_USDT": [_trade(1, "BUY", "1700000000", "BTC_USDT"), _trade(2, "sell", "1700000500", "BTC_USDT")],
    "BTC_ETH": [_trade(3, "weird", "1690000000")],
    "ETH_USDT": [_trade(4, "buy", "1700000900"), _trade(5, "sell", "not-a-time")],
    "SOL_USDT": [_trade(100 + i, "buy", str(1700000000 + i), "SOL_USDT") for i in range(120)],
}


def _my_trades(request: httpx.Request) -> list[dict[str, Any]]:
    query = dict(parse_qsl(request.url.query.decode()))
    size, page = int(query["limit"]), int(query["page"])
    return BOOK.get(query["currency_pair"], [])[(page - 1) * size : page * size]


async def _tally(trades: Awaitable[list[Any]]) -> dict[str, Any]:
    rows = await trades
    return {"count": len(rows), "newest": rows[0], "oldest": rows[-1]}


def _deposit(index: int, status: str) -> dict[str, Any]:
    return {
        "id": f"d{index}",
        "currency": "USDT",
        "amount": "100.5",
        "timestamp": str(1700000000 + index),
        "status": status,
        "txid": f"0x{index}",
    }


def _withdrawal(index: int, status: str) -> dict[str, Any]:
    return {
        "id": f"w{index}",
        "currency": "BTC",
        "amount": "0.2",
        "fee": "0.0001",
        "timestamp": str(1700000000 + index),
        "status": status,
        "txid": f"tx{index}",
        "address": "bc1q",
    }


async def test_gateio_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = GateIOService("key", "secret")
    api.on("GET", ACCOUNTS, ACCOUNT_ROWS)
    api.on("GET", MY_TRADES, _my_trades)
    api.on("GET", DEPOSITS, [*[_deposit(i, s) for i, s in enumerate(DEPOSIT_STATUSES)], {"id": 7}])
    api.on("GET", WITHDRAWALS, [*[_withdrawal(i, s) for i, s in enumerate(WITHDRAWAL_STATUSES)], {"id": 8}])
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "trades_from_balances": await record(api, client.get_trades),
        "trades_limited_across_pairs": await record(api, lambda: client.get_trades(limit=3)),
        "trades_paginated": await record(api, lambda: _tally(client.get_trades("SOL_USDT", SINCE, UNTIL, limit=150))),
        "trades_unknown_pair": await record(api, lambda: client.get_trades("XRP_USDT")),
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits("USDT", SINCE, limit=2)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(api, lambda: client.get_withdrawals("BTC", SINCE, limit=3)),
        "fiat_orders": await record(api, client.get_fiat_orders),
        "connection_error": await record(api, client.connection_error),
    }

    api.scripts.clear()
    for path in (ACCOUNTS, MY_TRADES, DEPOSITS, WITHDRAWALS):
        api.on("GET", path, REFUSED, status=401)
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["trades_refused"] = await record(api, lambda: client.get_trades("BTC_USDT"))
    observed["trades_without_balances"] = await record(api, client.get_trades)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)

    api.scripts.clear()
    for path in (ACCOUNTS, DEPOSITS, WITHDRAWALS):
        api.on("GET", path, [])
    api.on("GET", MY_TRADES, BOOK["SOL_USDT"][:100])
    api.on("GET", MY_TRADES, REFUSED, status=500)
    observed["balances_empty"] = await record(api, client.get_balances)
    observed["trades_no_pairs"] = await record(api, client.get_trades)
    observed["trades_page_two_error"] = await record(api, lambda: _tally(client.get_trades("SOL_USDT", limit=150)))
    observed["deposits_empty"] = await record(api, client.get_deposits)
    observed["withdrawals_empty"] = await record(api, client.get_withdrawals)
    assert_golden("gateio", observed)
