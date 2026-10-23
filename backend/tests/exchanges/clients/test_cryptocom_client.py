import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

import app.services.exchanges.cryptocom as module
from app.services.exchanges.cryptocom import CryptoComService
from tests.exchanges.clients.harness import ScriptedApi, assert_golden, install, record

SUMMARY = "/v2/private/get-account-summary"
TRADES = "/v2/private/get-trades"
DEPOSITS = "/v2/private/get-deposit-history"
WITHDRAWALS = "/v2/private/get-withdrawal-history"
EMPTY_TRADES = {"code": 0, "result": {"trade_list": []}}
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 30, tzinfo=UTC)


class CryptoComApi:
    def __init__(self, api: ScriptedApi) -> None:
        self.api = api
        self.seen: list[dict[str, Any]] = []

    def on(self, path: str, default: Any, answers: dict[str, Any] | None = None, status: int = 200) -> None:
        def answer(request: httpx.Request) -> Any:
            params = json.loads(request.content)["params"]
            self.seen.append(params)
            return (answers or {}).get(params.get("instrument_name", ""), default)

        self.api.on("POST", path, answer, status=status)

    async def observe(self, call: Callable[[], Awaitable[Any]]) -> dict[str, Any]:
        self.seen.clear()
        observed = await record(self.api, call)
        return {**observed, "params": sorted(self.seen, key=lambda p: json.dumps(p, sort_keys=True))}


def _trade(trade_id: Any, instrument: str | None, side: str, ts: int, **extra: Any) -> dict[str, Any]:
    trade = {"trade_id": trade_id, "side": side, "traded_quantity": "0.5", "traded_price": 30000.25, "create_time": ts}
    if instrument is not None:
        trade["instrument_name"] = instrument
    return {**trade, **extra}


def _trades(*trades: dict[str, Any]) -> dict[str, Any]:
    return {"code": 0, "result": {"trade_list": list(trades)}}


def _movement(**fields: Any) -> dict[str, Any]:
    return {"currency": "ETH", "amount": "1.5", "create_time": 1700000000000, **fields}


ACCOUNTS = {
    "code": 0,
    "result": {
        "accounts": [
            {"currency": "BTC", "balance": 0.5, "available": 0.4},
            {"currency": "ETH", "balance": "2", "available": "2"},
            {"currency": "CRO", "balance": "1000"},
            {"currency": "SOL", "balance": "3", "available": "1.5"},
            {"currency": "EUR", "balance": "150", "available": "150"},
            {"currency": "DUST", "balance": 0, "available": 0},
            {"currency": "NEG", "balance": "-1"},
            {"currency": "MISS"},
        ]
    },
}

TRADE_ANSWERS = {
    "BTC_USDT": _trades(
        _trade("t1", "BTC_USDT", "BUY", 1700000000000, fee="0.15", fee_currency="USDT"),
        _trade(2, "BTC_USDT", "Sell", 1700000300000),
    ),
    "ETH_BTC": _trades(_trade("t3", "ETH_BTC", "buy", 1700000200000, fee=0.0001, fee_currency="BTC")),
    "CRO_USDT": {"code": 10002, "message": "UNAUTHORIZED"},
    "SOL_USD": {"code": 0},
    "ETH_CRO": {"code": 0, "result": {}},
    "SOL_EUR": _trades(
        _trade("t4", "SOL_EUR", "sell", 1700000100000),
        {"trade_id": "bad", "side": "buy", "create_time": 1700000500000},
    ),
    "BTC_ETH": _trades(
        _trade("t5", "BTC_EUR", "buy", 1700000400000),
        _trade("t6", None, "buy", 1700000410000),
        _trade("t7", "BTC_ETH_X", "buy", 1700000420000),
        _trade("t8", "BTC_ETH", "SELL", 1700000430000),
    ),
    "USDC_USDT": _trades(_trade(42, "USDC_USDT", "buy", 1700000440000)),
}

DEPOSIT_LIST = {
    "code": 0,
    "result": {
        "deposit_list": [
            _movement(id=11, status=0, txid="0xa"),
            _movement(id="d2", status=1),
            _movement(id="d3", status=2, amount=0.25),
            _movement(id="d4", status=3),
            _movement(status=9),
            _movement(id="d6"),
            _movement(id="d7", status="2"),
            {"id": "d8", "currency": "ETH", "create_time": 1700000000000},
            _movement(id="d9", status=2),
        ]
    },
}

WITHDRAWAL_LIST = {
    "code": 0,
    "result": {
        "withdrawal_list": [
            _movement(id=21, currency="BTC", status=0, fee="0.0005", txid="tx1", address="bc1q"),
            _movement(id="w2", currency="BTC", status=1, fee=0.001),
            _movement(id="w3", currency="BTC", status=2),
            _movement(id="w4", currency="BTC", status=3),
            _movement(id="w5", currency="BTC", status=4),
            _movement(currency="BTC", status=7),
            _movement(id="w7", currency="BTC"),
            {"id": "w8", "amount": "1", "create_time": 1700000000000},
            _movement(id="w9", currency="BTC", status=2),
        ]
    },
}


async def test_cryptocom_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = CryptoComApi(install(monkeypatch, module))
    client = CryptoComService("key", "secret")
    api.on(SUMMARY, ACCOUNTS)
    api.on(TRADES, EMPTY_TRADES, TRADE_ANSWERS)
    api.on(DEPOSITS, DEPOSIT_LIST)
    api.on(WITHDRAWALS, WITHDRAWAL_LIST)
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "normalize_symbol": {s: client.normalize_symbol(s) for s in ("BTC_USDT", "ETHBTC", "CRO", "USDT")},
        "connection_error": await api.observe(client.connection_error),
        "fiat_orders": await api.observe(client.get_fiat_orders),
        "test_connection": await api.observe(client.test_connection),
        "balances": await api.observe(client.get_balances),
        "trades": await api.observe(client.get_trades),
        "trades_for_symbol": await api.observe(lambda: client.get_trades("ETH", START, END, limit=50)),
        "trades_for_quote_symbol": await api.observe(lambda: client.get_trades("USDT", limit=500)),
        "conversions": await api.observe(lambda: client.get_crypto_conversions(limit=50)),
        "deposits": await api.observe(lambda: client.get_deposits("ETH", START, limit=500)),
        "deposits_default": await api.observe(client.get_deposits),
        "withdrawals": await api.observe(lambda: client.get_withdrawals("BTC", START, limit=20)),
        "withdrawals_default": await api.observe(client.get_withdrawals),
    }
    api.api.scripts.clear()
    api.on(SUMMARY, {"code": 40101, "message": "UNAUTHORIZED"})
    api.on(TRADES, EMPTY_TRADES)
    api.on(DEPOSITS, {"code": 10003, "message": "IP_ILLEGAL"})
    api.on(WITHDRAWALS, {"code": 0})
    observed["connection_refused"] = await api.observe(client.test_connection)
    observed["balances_refused"] = await api.observe(client.get_balances)
    observed["trades_without_balances"] = await api.observe(client.get_trades)
    observed["conversions_without_balances"] = await api.observe(client.get_crypto_conversions)
    observed["deposits_refused"] = await api.observe(client.get_deposits)
    observed["withdrawals_without_result"] = await api.observe(client.get_withdrawals)
    api.api.scripts.clear()
    api.on(SUMMARY, {"code": 0}, status=500)
    api.on(TRADES, EMPTY_TRADES, status=503)
    api.on(WITHDRAWALS, WITHDRAWAL_LIST, status=500)
    observed["connection_http_error"] = await api.observe(client.test_connection)
    observed["balances_http_error"] = await api.observe(client.get_balances)
    observed["trades_http_error"] = await api.observe(lambda: client.get_trades("BTC"))
    observed["deposits_not_scripted"] = await api.observe(client.get_deposits)
    observed["withdrawals_http_error"] = await api.observe(client.get_withdrawals)
    api.api.scripts.clear()
    api.on(SUMMARY, {"code": "0", "result": ACCOUNTS["result"]})
    api.on(SUMMARY, {"code": 0})
    api.on(DEPOSITS, {"code": 0, "result": {"deposit_list": []}})
    observed["connection_string_code"] = await api.observe(client.test_connection)
    observed["balances_without_result"] = await api.observe(client.get_balances)
    observed["deposits_empty"] = await api.observe(client.get_deposits)
    assert_golden("cryptocom", observed)
