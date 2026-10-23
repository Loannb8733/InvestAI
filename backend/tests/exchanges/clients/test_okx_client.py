from typing import Any

import pytest

import app.services.exchanges.okx as module
from app.services.exchanges.okx import OkxService
from tests.exchanges.clients.harness import assert_golden, install, record

OK = "0"


def _fill(trade_id: str, bill: str, side: str, ts: str) -> dict[str, Any]:
    return {
        "tradeId": trade_id,
        "billId": bill,
        "instId": "BTC-USDT",
        "side": side,
        "fillSz": "0.01",
        "fillPx": "60000.5",
        "fee": "-0.6",
        "feeCcy": "USDT",
        "ts": ts,
    }


async def test_okx_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = OkxService("key", "secret", "pass")
    api.on(
        "GET",
        "/api/v5/account/balance",
        {
            "code": OK,
            "data": [
                {
                    "details": [
                        {"ccy": "BTC", "availBal": "0.5", "frozenBal": "0.1"},
                        {"ccy": "DUST", "availBal": "0", "frozenBal": ""},
                    ]
                }
            ],
        },
    )
    api.on(
        "GET",
        "/api/v5/trade/fills-history",
        {"code": OK, "data": [_fill("t1", "b1", "buy", "1700000000000"), _fill("t2", "b2", "SELL", "1700000100000")]},
        {"code": OK, "data": [_fill("t3", "", "weird", "1690000000000")]},
    )
    api.on(
        "GET",
        "/api/v5/asset/deposit-history",
        {
            "code": OK,
            "data": [
                {"depId": "d1", "ccy": "ETH", "amt": "1.5", "ts": "1700000000000", "state": "2", "txId": "0xabc"},
                {"depId": "d2", "ccy": "ETH", "amt": "2", "ts": "1700000000000", "state": "99"},
            ],
        },
    )
    api.on(
        "GET",
        "/api/v5/asset/withdrawal-history",
        {
            "code": OK,
            "data": [
                {
                    "wdId": "w1",
                    "ccy": "BTC",
                    "amt": "0.2",
                    "fee": "0.0001",
                    "ts": "1700000000000",
                    "state": "2",
                    "txId": "tx",
                    "to": "bc1q",
                },
                {"wdId": "w2", "ccy": "BTC", "amt": "0.3", "fee": "0", "ts": "1700000000000", "state": "-2"},
            ],
        },
    )
    observed = {
        "test_connection": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "trades": await record(api, lambda: client.get_trades(limit=250)),
        "deposits": await record(api, client.get_deposits),
        "withdrawals": await record(api, client.get_withdrawals),
    }
    api.scripts.clear()
    api.on("GET", "/api/v5/account/balance", {"code": "50113", "msg": "Invalid Sign"})
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["connection_refused"] = await record(api, client.test_connection)
    assert_golden("okx", observed)
