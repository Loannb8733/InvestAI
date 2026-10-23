from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

from app.domains.exchanges.connectors.bitstamp import movements, trades
from app.domains.exchanges.connectors.bitstamp.connector import BitstampService
from tests.exchanges.clients.harness import assert_golden, install, record

BALANCE = "/api/v2/balance/"
LEDGER = "/api/v2/user_transactions/"
PAGE_SIZE = 100
REFUSED = {"status": "error", "reason": "Invalid signature", "code": "API0005"}


def _tx(tx_id: int, tx_type: str | int, when: str, **amounts: Any) -> dict[str, Any]:
    return {"id": tx_id, "type": tx_type, "datetime": when, **amounts}


def _page(*txs: dict[str, Any]) -> list[dict[str, Any]]:
    fillers = [_tx(900 + i, "14", "2023-10-01 00:00:00", btc="0.1") for i in range(PAGE_SIZE - len(txs))]
    return [*txs, *fillers]


def _ledger(pages: dict[int, list[dict[str, Any]]]) -> Callable[[httpx.Request], Any]:
    def serve(request: httpx.Request) -> Any:
        return pages.get(int(dict(parse_qsl(request.content.decode()))["offset"]), [])

    return serve


BALANCE_SHEET = {
    "btc_balance": "0.50000000",
    "btc_available": "0.40000000",
    "btc_reserved": "0.10000000",
    "eth_balance": "0.00000000",
    "eth_available": "0.00000000",
    "eth_reserved": "0.00000000",
    "usd_balance": "100.50",
    "usd_available": "100.50",
    "xyz_balance": "3",
    "xyz_available": "2.5",
    "xyz_reserved": "0.5",
    "abc_balance": "0",
    "btcusd_fee": "0.500",
}

RECENT = _page(
    _tx(1, "2", "2023-11-14 22:13:20", btc="0.01", usd="-370.00", eur="0.0", fee="0.74", order_id=11),
    _tx(2, 2, "2023-11-13 10:00:00", eth="-1.5", eur="3000", fee="6"),
    _tx(3, "2", "2023-11-12 09:30:00.250000", btc="-0.1", eth="2"),
    _tx(4, "2", "2023-11-11 08:00:00", btc="0.02", usd="-740", btc_usd="37000", fee="1.48"),
    _tx(5, "2", "2023-11-10 07:00:00", btc="0.5", fee="0"),
    _tx(6, "0", "2023-11-09 06:00:00", btc="0.0", usd=None, eur="500", fee="0"),
    _tx(7, 0, "2023-11-08 05:00:00", btc="0.25"),
    _tx(8, "0", "2023-11-07 04:00:00", btc="0", fee="0"),
    _tx(9, "1", "2023-11-06 03:00:00", eth="-0.75", fee="0.001"),
    _tx(10, 1, "2023-11-05 02:00:00", eur="-200"),
    _tx(11, "1", "2023-11-04 01:00:00", btc="0.3"),
)

OLDER = [
    _tx(20, "2", "2022-06-01 12:00:00", btc="0.001", eur="-25", fee="0.1"),
    _tx(21, "0", "2022-05-01 12:00:00", eth="3"),
    _tx(22, "1", "2022-04-01 12:00:00", btc="-0.05", fee="0.0005"),
]


async def test_bitstamp_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, trades, movements)
    client = BitstampService("key", "secret")
    api.on("POST", BALANCE, BALANCE_SHEET)
    api.on("POST", LEDGER, _ledger({0: RECENT, PAGE_SIZE: OLDER}))
    since = datetime(2023, 1, 1)
    start, end = datetime(2023, 11, 11), datetime(2023, 11, 13, 12)
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "trades": await record(api, client.get_trades),
        "trades_limited": await record(api, lambda: client.get_trades(limit=2)),
        "trades_window": await record(api, lambda: client.get_trades(start_time=start, end_time=end)),
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits(symbol="btc", start_time=since)),
        "deposits_limited": await record(api, lambda: client.get_deposits(limit=1)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(api, lambda: client.get_withdrawals(symbol="eth", start_time=since)),
        "withdrawals_limited": await record(api, lambda: client.get_withdrawals(limit=1)),
        "connection_error": await record(api, client.connection_error),
        "fiat_orders": await record(api, client.get_fiat_orders),
    }
    api.scripts.clear()
    api.on("POST", LEDGER, _ledger({0: _page(_tx(30, "2", "2023-11-14 22:13:20", btc="0.01", usd="-370"))}))
    observed["trades_empty_next_page"] = await record(api, client.get_trades)
    api.scripts.clear()
    api.on("POST", LEDGER, [])
    observed["trades_empty"] = await record(api, client.get_trades)
    api.scripts.clear()
    api.on("POST", LEDGER, {"status": "error", "reason": "Invalid nonce", "code": "API0004"})
    observed["trades_error_body"] = await record(api, client.get_trades)
    observed["deposits_error_body"] = await record(api, client.get_deposits)
    observed["withdrawals_error_body"] = await record(api, client.get_withdrawals)
    api.scripts.clear()
    api.on("POST", BALANCE, REFUSED, status=403)
    api.on("POST", LEDGER, REFUSED, status=403)
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["trades_refused"] = await record(api, client.get_trades)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)
    unsigned = BitstampService("key")
    observed["unsigned_connection"] = await record(api, unsigned.test_connection)
    observed["unsigned_balances"] = await record(api, unsigned.get_balances)
    observed["unsigned_trades"] = await record(api, unsigned.get_trades)
    assert_golden("bitstamp", observed)
