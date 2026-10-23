from datetime import datetime
from typing import Any

import pytest

import app.services.exchanges.bitpanda as module
from app.services.exchanges.bitpanda import BitpandaService
from tests.exchanges.clients.harness import assert_golden, install, record

BALANCES = "/api/v1/account/balances"
TRADES = "/api/v1/account/trades"
DEPOSITS = "/api/v1/account/deposits"
WITHDRAWALS = "/api/v1/account/withdrawals"
REFUSED = {"error": "INVALID_APIKEY"}


def _trade(trade_id: str | int, side: str, time: str, **fee: str) -> dict[str, Any]:
    trade: dict[str, Any] = {
        "trade_id": trade_id,
        "instrument_code": "BTC_EUR",
        "side": side,
        "amount": "0.01",
        "price": "60000.5",
        "time": time,
    }
    return trade | ({"fee": fee} if fee else {})


BALANCE_ROWS = [
    {"currency_code": "BTC", "available": "0.5", "locked": "0.1"},
    {"currency_code": "EUR", "available": "0", "locked": "0"},
    {"currency_code": "ETH", "available": "1.2"},
    {"available": "0", "locked": "3"},
]

TRADE_PAGES: dict[str | None, dict[str, Any]] = {
    None: {
        "trade_history": [
            _trade("t1", "BUY", "2023-11-14T22:13:20.123Z", fee_amount="0.00001", fee_currency="BTC"),
            _trade(2, "SELL", "2023-11-15T08:00:00Z", fee_amount="0.6", fee_currency="EUR"),
        ],
        "cursor": "page-2",
    },
    "page-2": {"trade_history": [_trade("t3", "buy", "2023-11-01T00:00:00+00:00")], "cursor": ""},
}

DEPOSIT_ROWS = [
    {
        "transaction_id": "d1",
        "currency_code": "BTC",
        "amount": "0.5",
        "time": "2023-11-14T22:13:20Z",
        "status": "settled",
        "blockchain_transaction_id": "0xabc",
    },
    {"transaction_id": 42, "currency_code": "EUR", "amount": "250", "time": "2023-11-10T10:00:00.500Z"},
    {
        "transaction_id": "d3",
        "currency_code": "BTC",
        "amount": "0.1",
        "time": "2023-11-01T00:00:00Z",
        "status": "pending",
    },
]

WITHDRAWAL_ROWS = [
    {
        "transaction_id": "w1",
        "currency_code": "ETH",
        "amount": "1.2",
        "fee": "0.005",
        "time": "2023-11-14T22:13:20Z",
        "status": "SETTLED",
        "blockchain_transaction_id": "0xdef",
        "recipient_address": "0xrecipient",
    },
    {"transaction_id": 7, "currency_code": "EUR", "amount": "100", "time": "2023-11-12T09:00:00Z"},
    {
        "transaction_id": "w3",
        "currency_code": "BTC",
        "amount": "0.2",
        "fee": "0.0001",
        "time": "2023-11-01T00:00:00Z",
        "status": "pending",
    },
]


async def test_bitpanda_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = BitpandaService("token")
    api.on("GET", BALANCES, BALANCE_ROWS)
    api.on("GET", TRADES, lambda request: TRADE_PAGES[request.url.params.get("cursor")])
    api.on("GET", DEPOSITS, {"deposit_history": DEPOSIT_ROWS})
    api.on("GET", WITHDRAWALS, {"withdrawal_history": WITHDRAWAL_ROWS})
    since, until = datetime(2023, 1, 1), datetime(2023, 12, 31)
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "trades": await record(api, client.get_trades),
        "trades_limited": await record(api, lambda: client.get_trades(limit=1)),
        "trades_filtered": await record(
            api, lambda: client.get_trades(symbol="BTC_EUR", start_time=since, end_time=until)
        ),
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits(symbol="BTC", start_time=since, limit=2)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(
            api, lambda: client.get_withdrawals(symbol="ETH", start_time=since, limit=2)
        ),
        "connection_error": await record(api, client.connection_error),
        "fiat_orders": await record(api, client.get_fiat_orders),
    }
    api.scripts.clear()
    api.on("GET", BALANCES, {"account_id": "acc-1", "balances": BALANCE_ROWS})
    api.on(
        "GET",
        TRADES,
        {"trade_history": [_trade("t4", "BUY", "2023-11-16T00:00:00Z"), {"trade_id": "t5"}], "cursor": "page-9"},
        {"trade_history": [], "cursor": "page-9"},
    )
    api.on("GET", DEPOSITS, DEPOSIT_ROWS, {"unexpected": []})
    api.on("GET", WITHDRAWALS, WITHDRAWAL_ROWS, {"unexpected": []})
    observed["balances_wrapped"] = await record(api, client.get_balances)
    observed["trades_malformed"] = await record(api, client.get_trades)
    observed["trades_empty"] = await record(api, client.get_trades)
    observed["deposits_bare_list"] = await record(api, client.get_deposits)
    observed["deposits_unknown_shape"] = await record(api, client.get_deposits)
    observed["withdrawals_bare_list"] = await record(api, client.get_withdrawals)
    observed["withdrawals_unknown_shape"] = await record(api, client.get_withdrawals)
    api.scripts.clear()
    for path in (BALANCES, TRADES, DEPOSITS, WITHDRAWALS):
        api.on("GET", path, REFUSED, status=401)
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["trades_refused"] = await record(api, client.get_trades)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)
    assert_golden("bitpanda", observed)
