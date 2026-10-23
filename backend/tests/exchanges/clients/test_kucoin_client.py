from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

import app.services.exchanges.kucoin as module
from app.services.exchanges.kucoin import KuCoinService
from tests.exchanges.clients.harness import assert_golden, install, record

OK = "200000"
ACCOUNTS = "/api/v1/accounts"
FILLS = "/api/v1/fills"
DEPOSITS = "/api/v1/deposits"
WITHDRAWALS = "/api/v1/withdrawals"
SINCE = datetime(2026, 1, 1, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, tzinfo=UTC)
REFUSED = {"code": "400005", "msg": "Invalid KC-API-SIGN"}
DOWN = {"msg": "down"}


def _page(*items: dict[str, Any], total: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"items": list(items)}
    if total is not None:
        data["totalPage"] = total
    return {"code": OK, "data": data}


def _paged(*pages: dict[str, Any]) -> Callable[[httpx.Request], Any]:
    return lambda request: pages[int(request.url.params["currentPage"]) - 1]


def _fill(trade_id: str, symbol: str, side: str, created_at: int | str) -> dict[str, Any]:
    return {
        "tradeId": trade_id,
        "symbol": symbol,
        "side": side,
        "size": "0.01",
        "price": "60000.5",
        "fee": "0.6",
        "feeCurrency": "USDT",
        "createdAt": created_at,
    }


def _deposit(key: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"id": key, "currency": "ETH", "amount": "1.5", "createdAt": 1700000000000, "status": status, **extra}


def _withdrawal(key: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": key,
        "currency": "BTC",
        "amount": "0.2",
        "fee": "0.0001",
        "createdAt": 1700000000000,
        "status": status,
        **extra,
    }


async def test_kucoin_client_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = KuCoinService("key", "secret", "pass")
    api.on(
        "GET",
        ACCOUNTS,
        {
            "code": OK,
            "data": [
                {"currency": "BTC", "available": "0.5", "holds": "0.1"},
                {"currency": "USDT", "available": "100"},
                {"currency": "DUST", "available": "0", "holds": "0"},
            ],
        },
    )
    api.on(
        "GET",
        FILLS,
        _paged(
            _page(
                _fill("t1", "BTC-USDT", "buy", 1700000000000), _fill("t2", "BTC-USDT", "SELL", 1700000100000), total=2
            ),
            _page(_fill("t3", "ETH-USDT", "Buy", "1690000000000"), total=2),
        ),
    )
    api.on(
        "GET",
        DEPOSITS,
        _page(
            _deposit("d1", "SUCCESS", walletTxId="0xabc"),
            _deposit("d2", "PROCESSING"),
            _deposit("d3", "FAILURE"),
            _deposit("d4", "CANCELLED"),
        ),
    )
    api.on(
        "GET",
        WITHDRAWALS,
        _paged(
            _page(_withdrawal("w1", "PROCESSING"), _withdrawal("w2", "WALLET_PROCESSING"), total=2),
            _page(
                _withdrawal("w3", "SUCCESS", walletTxId="txw3", address="bc1qxyz"),
                _withdrawal("w4", "FAILURE"),
                _withdrawal("w5", "REVIEW"),
                total=2,
            ),
        ),
    )
    observed = {
        "exchange_name": client.exchange_name,
        "normalize_symbol": {s: client.normalize_symbol(s) for s in ("BTC-USDT", "ETH")},
        "test_connection": await record(api, client.test_connection),
        "connection_error": await record(api, client.connection_error),
        "balances": await record(api, client.get_balances),
        "trades": await record(api, lambda: client.get_trades(symbol="BTC-USDT", start_time=SINCE, end_time=UNTIL)),
        "trades_limited": await record(api, lambda: client.get_trades(limit=1)),
        "deposits": await record(api, lambda: client.get_deposits(symbol="ETH", start_time=SINCE)),
        "deposits_limited": await record(api, lambda: client.get_deposits(limit=2)),
        "withdrawals": await record(api, lambda: client.get_withdrawals(symbol="BTC", start_time=SINCE)),
        "withdrawals_limited": await record(api, lambda: client.get_withdrawals(limit=3)),
        "fiat_orders": await record(api, client.get_fiat_orders),
    }
    api.scripts.clear()
    api.on("GET", ACCOUNTS, REFUSED, REFUSED)
    api.on("GET", ACCOUNTS, DOWN, status=500)
    api.on("GET", FILLS, REFUSED)
    api.on("GET", FILLS, DOWN, status=500)
    api.on("GET", FILLS, _page(_fill("t4", "BTC-USDT", "buy", 1700000000000), _fill("t5", "BTC-USDT", "buy", "oops")))
    api.on("GET", DEPOSITS, REFUSED)
    api.on("GET", DEPOSITS, _page())
    api.on("GET", WITHDRAWALS, DOWN, status=503)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_http_error"] = await record(api, client.get_balances)
    observed["connection_http_error"] = await record(api, client.test_connection)
    observed["trades_refused"] = await record(api, client.get_trades)
    observed["trades_http_error"] = await record(api, client.get_trades)
    observed["trades_malformed"] = await record(api, client.get_trades)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["deposits_empty"] = await record(api, client.get_deposits)
    observed["withdrawals_http_error"] = await record(api, client.get_withdrawals)
    keyless = KuCoinService("key")
    observed["connection_without_secret"] = await record(api, keyless.test_connection)
    observed["balances_without_secret"] = await record(api, keyless.get_balances)
    assert_golden("kucoin", observed)
