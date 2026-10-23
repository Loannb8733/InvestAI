from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.domains.exchanges.connectors.bybit import trades as bybit_trades
from app.domains.exchanges.connectors.bybit import transfers as bybit_transfers
from app.domains.exchanges.connectors.bybit.connector import BybitService
from tests.exchanges.clients.harness import assert_golden, install, record

GLOBAL = "api.bybit.com"
EU = "api.bybit.nl"
WALLET = "/v5/account/wallet-balance"
EXECUTIONS = "/v5/execution/list"
DEPOSITS = "/v5/asset/deposit/query-record"
WITHDRAWALS = "/v5/asset/withdraw/query-record"
REFUSED = {"retCode": 10003, "retMsg": "API key is invalid."}
BOOM = {"retMsg": "boom"}
SINCE = datetime(2026, 1, 1, tzinfo=UTC)
UNTIL = datetime(2026, 9, 1, tzinfo=UTC)
WALLET_OK = {
    "retCode": 0,
    "result": {
        "list": [
            {
                "coin": [
                    {"coin": "BTC", "availableToWithdraw": "0.4", "locked": "0.1", "walletBalance": "0.5"},
                    {"coin": "DUST", "availableToWithdraw": "0", "locked": "0", "walletBalance": "0"},
                ]
            },
            {"coin": [{"coin": "ETH", "walletBalance": "2"}]},
        ]
    },
}
WALLET_BLANK = {
    "retCode": 0,
    "result": {
        "list": [
            {
                "coin": [
                    {"coin": "BTC", "availableToWithdraw": "0.4", "locked": "0.1", "walletBalance": "0.5"},
                    {"coin": "SOL", "availableToWithdraw": "", "locked": "0", "walletBalance": "3"},
                    {"coin": "ETH", "availableToWithdraw": "2", "locked": "0", "walletBalance": "2"},
                ]
            }
        ]
    },
}
WITHDRAWAL_STATUSES = [
    "SecurityCheck",
    "Pending",
    "success",
    "CancelByUser",
    "Reject",
    "Fail",
    "BlockchainConfirmed",
    "Other",
]


def _wallet(*working: str, down: str = "") -> Callable[[httpx.Request], Any]:
    def answer(request: httpx.Request) -> Any:
        if request.url.host == down:
            raise httpx.ConnectError("unreachable", request=request)
        return WALLET_OK if request.url.host in working else REFUSED

    return answer


def _execution(exec_id: str, side: str, exec_time: str) -> dict[str, Any]:
    return {
        "execId": exec_id,
        "symbol": "BTCUSDT",
        "side": side,
        "execQty": "0.01",
        "execPrice": "60000.5",
        "execFee": "0.0006",
        "feeCurrency": "BTC",
        "execTime": exec_time,
    }


def _page(rows: list[dict[str, Any]], cursor: str = "") -> dict[str, Any]:
    return {"retCode": 0, "result": {"list": rows, "nextPageCursor": cursor}}


def _rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"retCode": 0, "result": {"rows": rows}}


def _deposit(dep_id: str, status: int, success_at: str) -> dict[str, Any]:
    return {"id": dep_id, "coin": "USDT", "amount": "100.5", "status": status, "successAt": success_at, "txID": "0x1"}


def _withdrawal(index: int, status: str) -> dict[str, Any]:
    return {
        "withdrawId": f"w{index}",
        "coin": "BTC",
        "amount": "0.2",
        "withdrawFee": "0.0001",
        "createTime": str(1700000000000 + index) if index else "0",
        "status": status,
        "txID": f"tx{index}",
        "toAddress": "bc1q",
    }


DEPOSIT_ROWS = [
    _deposit("d1", 3, "1700000000000"),
    _deposit("d2", 1, "1700000100000"),
    _deposit("d3", 2, "1700000200000"),
    _deposit("d4", 4, "1700000300000"),
    _deposit("d5", 0, "0"),
    _deposit("d6", 7, "1700000400000"),
    {"id": "d7", "coin": "ETH", "amount": "1"},
]


async def test_bybit_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, bybit_trades, bybit_transfers)
    client = BybitService("key", "secret")
    api.on("GET", WALLET, _wallet(GLOBAL))
    api.on(
        "GET",
        EXECUTIONS,
        _page([_execution("t1", "Buy", "1700000000000"), _execution("t2", "SELL", "1700000100000")], "p2"),
        _page([_execution("t3", "weird", "1690000000000"), {"execId": "t4"}], "p3"),
    )
    api.on("GET", DEPOSITS, _rows(DEPOSIT_ROWS))
    api.on("GET", WITHDRAWALS, _rows([_withdrawal(i, s) for i, s in enumerate(WITHDRAWAL_STATUSES)]))
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "connection_cached": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "balances_fresh_client": await record(api, BybitService("key", "secret").get_balances),
        "trades": await record(
            api, lambda: client.get_trades(symbol="BTCUSDT", start_time=SINCE, end_time=UNTIL, limit=3)
        ),
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits("USDT", SINCE, limit=500)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(api, lambda: client.get_withdrawals("BTC", SINCE, limit=500)),
        "fiat_orders": await record(api, client.get_fiat_orders),
        "connection_error": await record(api, client.connection_error),
    }

    api.scripts.clear()
    for path in (WALLET, EXECUTIONS, DEPOSITS, WITHDRAWALS):
        api.on("GET", path, REFUSED)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["trades_refused"] = await record(api, client.get_trades)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)

    api.scripts.clear()
    for path in (WALLET, DEPOSITS, WITHDRAWALS):
        api.on("GET", path, BOOM, status=500)
    api.on("GET", EXECUTIONS, _page([_execution("t1", "Buy", "1700000000000")], "p2"))
    api.on("GET", EXECUTIONS, BOOM, status=500)
    observed["balances_http_error"] = await record(api, client.get_balances)
    observed["trades_partial_http_error"] = await record(api, client.get_trades)
    observed["deposits_http_error"] = await record(api, client.get_deposits)
    observed["withdrawals_http_error"] = await record(api, client.get_withdrawals)

    api.scripts.clear()
    api.on("GET", WALLET, WALLET_BLANK)
    api.on("GET", EXECUTIONS, _page([_execution("t1", "Buy", "1700000000000")], "p2"), _page([], "p3"))
    api.on("GET", DEPOSITS, {"retCode": 0, "result": {}})
    api.on("GET", WITHDRAWALS, {"retCode": 0, "result": {}})
    observed["balances_blank_field"] = await record(api, client.get_balances)
    observed["trades_until_empty_page"] = await record(api, client.get_trades)
    observed["deposits_empty"] = await record(api, client.get_deposits)
    observed["withdrawals_empty"] = await record(api, client.get_withdrawals)

    api.scripts.clear()
    api.on("GET", WALLET, _wallet(EU))
    api.on("GET", EXECUTIONS, _page([_execution("t1", "Buy", "1700000000000")]))
    eu_client = BybitService("key", "secret")
    observed["connection_eu_fallback"] = await record(api, eu_client.test_connection)
    observed["eu_base_url"] = eu_client.BASE_URL
    observed["trades_after_eu_fallback"] = await record(api, eu_client.get_trades)
    observed["trades_without_resolution"] = await record(api, BybitService("key", "secret").get_trades)
    observed["balances_after_eu_fallback"] = await record(api, BybitService("key", "secret").get_balances)

    api.scripts.clear()
    api.on("GET", WALLET, _wallet(EU, down=GLOBAL))
    observed["connection_global_down"] = await record(api, BybitService("key", "secret").test_connection)

    api.scripts.clear()
    api.on("GET", WALLET, _wallet())
    unresolved = BybitService("key", "secret")
    observed["connection_refused_everywhere"] = await record(api, unresolved.test_connection)
    observed["unresolved_base_url"] = unresolved.BASE_URL
    observed["balances_unresolved"] = await record(api, unresolved.get_balances)
    assert_golden("bybit", observed)
