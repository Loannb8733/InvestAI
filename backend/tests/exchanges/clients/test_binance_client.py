from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.domains.exchanges.connectors.binance import conversions, core, earn, fiat, trades, transfers
from app.domains.exchanges.connectors.binance.connector import BinanceService
from tests.exchanges.clients.harness import FROZEN_NOW, ScriptedApi, assert_golden, install, record

T0 = 1_790_000_000_000
DAY_MS = 86_400_000
NOW_MS = int(FROZEN_NOW.timestamp() * 1000)
RECENT_REWARDS_START = NOW_MS - 29 * DAY_MS
JUN_1 = datetime(2026, 6, 1, tzinfo=UTC)
AUG_1 = datetime(2026, 8, 1, tzinfo=UTC)
SEP_1 = datetime(2026, 9, 1, tzinfo=UTC)
OCT_1 = datetime(2026, 10, 1, tzinfo=UTC)
INVALID_KEY = {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}
TOO_MANY = {"code": 345239, "msg": "Too many requests"}
TRADE_FLOW = "/sapi/v1/convert/tradeFlow"
AUTO_INVEST = "/sapi/v1/lending/auto-invest/history/list"
FLEXIBLE_REWARDS = "/sapi/v1/simple-earn/flexible/history/rewardsRecord"
LOCKED_REWARDS = "/sapi/v1/simple-earn/locked/history/rewardsRecord"
MODULES = (core, trades, transfers, fiat, conversions, earn)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _without(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in keys}


def _param(request: httpx.Request, name: str) -> str:
    return str(request.url.params.get(name, ""))


def _reset(api: ScriptedApi) -> None:
    api.scripts.clear()
    api.on("GET", "/api/v3/time", {"serverTime": NOW_MS})


async def _summary(call: Awaitable[list[Any]]) -> dict[str, Any]:
    items = await call
    return {"count": len(items), "newest": items[0], "oldest": items[-1]}


def _balance(asset: str, free: str, locked: str = "0") -> dict[str, str]:
    return {"asset": asset, "free": free, "locked": locked}


def _earn(asset: str, total: str) -> dict[str, Any]:
    return {"asset": asset, "totalAmount": total, "latestAnnualPercentageRate": "0.05", "canRedeem": True}


def _funding(asset: str, free: str, freeze: str = "0", withdrawing: str = "0") -> dict[str, str]:
    return {
        "asset": asset,
        "free": free,
        "locked": "0",
        "freeze": freeze,
        "withdrawing": withdrawing,
        "btcValuation": "0",
    }


ACCOUNT = {
    "makerCommission": 10,
    "canTrade": True,
    "accountType": "SPOT",
    "balances": [
        _balance("BTC", "0.5", "0.1"),
        _balance("ETH", "2"),
        _balance("LDETH", "1"),
        _balance("LDBNB", "2"),
        _balance("DOGE", "0"),
    ],
}


async def test_binance_account_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, *MODULES)
    _reset(api)
    client = BinanceService("key", "secret")
    api.on("GET", "/api/v3/account", ACCOUNT)
    api.on(
        "GET",
        "/sapi/v1/simple-earn/flexible/position",
        {"rows": [_earn("ETH", "0.6"), _earn("BTC", "0.2"), _earn("", "5")], "total": 150},
        {"rows": [_earn("SOL", "3"), _earn("ADA", "0")], "total": 150},
    )
    api.on(
        "GET", "/sapi/v1/simple-earn/locked/position", {"rows": [_earn("ETH", "0.45"), _earn("BNB", "1.5")], "total": 2}
    )
    api.on(
        "POST",
        "/sapi/v1/asset/get-funding-asset",
        [
            _funding("USDT", "10", freeze="1"),
            _funding("BTC", "0.05", withdrawing="0.01"),
            _funding("XRP", "0"),
            _funding("", "9"),
        ],
    )
    api.on(
        "GET",
        "/api/v3/exchangeInfo",
        {
            "symbols": [
                {"symbol": "USDTEUR", "status": "TRADING"},
                {"symbol": "BTCUSDT", "status": "TRADING"},
                {"symbol": "SOLUSDT", "status": "TRADING"},
            ]
        },
    )
    api.on("GET", "/api/v3/myTrades", [])
    observed: dict[str, Any] = {
        "exchange_name": client.exchange_name,
        "test_connection": await record(api, client.test_connection),
        "connection_error": await record(api, client.connection_error),
        "balances": await record(api, client.get_balances),
        "trades_after_balances": await record(api, client.get_trades),
    }

    _reset(api)
    api.on("GET", "/api/v3/account", ACCOUNT)
    api.on("GET", "/sapi/v1/simple-earn/flexible/position", {"rows": [_earn("ETH", "not-a-number")], "total": 1})
    api.on("GET", "/sapi/v1/simple-earn/locked/position", {"code": -1002, "msg": "unauthorized"}, status=401)
    api.on("POST", "/sapi/v1/asset/get-funding-asset", {"code": -1000, "msg": "unknown"})
    observed["balances_enrichment_failures"] = await record(api, BinanceService("key", "secret").get_balances)

    _reset(api)
    api.on("GET", "/api/v3/account", ACCOUNT)
    observed["balances_spot_only"] = await record(api, BinanceService("key", "secret").get_balances)

    _reset(api)
    api.on("GET", "/api/v3/account", INVALID_KEY, status=401)
    refused = BinanceService("key", "secret")
    observed["balances_refused"] = await record(api, refused.get_balances)
    observed["connection_refused"] = await record(api, refused.test_connection)
    observed["connection_error_refused"] = await record(api, refused.connection_error)

    _reset(api)
    api.on("GET", "/api/v3/account", [], status=500)
    observed["connection_error_unreadable"] = await record(api, BinanceService("key", "secret").connection_error)

    _reset(api)
    api.on("GET", "/api/v3/account", ACCOUNT)
    no_secret = BinanceService("key", None)
    observed["connection_without_secret"] = await record(api, no_secret.test_connection)
    observed["connection_error_without_secret"] = await record(api, no_secret.connection_error)
    observed["balances_without_secret"] = await record(api, no_secret.get_balances)
    assert_golden("binance", observed)


def _deposit(status: int, ts: int, **extra: Any) -> dict[str, Any]:
    return {
        "amount": "0.5",
        "coin": "BTC",
        "network": "BTC",
        "status": status,
        "address": "bc1q",
        "insertTime": ts,
        "transferType": 0,
        **extra,
    }


def _withdrawal(status: int, apply_time: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"w{status}",
        "amount": "0.2",
        "transactionFee": "0.0005",
        "coin": "BTC",
        "status": status,
        "applyTime": apply_time,
        "network": "BTC",
        **extra,
    }


DEPOSITS = [
    _deposit(1, T0, id="d1", txId="tx1"),
    _deposit(0, T0 + 1000, txId="tx2", coin="ETH", amount="10"),
    _deposit(6, T0 + 2000, coin="SOL", amount="3"),
    _deposit(7, T0 + 3000, id="d4", txId="tx4"),
]
WITHDRAWALS = [_withdrawal(s, f"2026-09-1{s} 08:30:00", address="bc1q", txId=f"tx{s}") for s in range(8)] + [
    _without(_withdrawal(9, "2026-09-20T09:00:00Z"), "transactionFee"),
]


async def test_binance_transfers_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, *MODULES)
    _reset(api)
    client = BinanceService("key", "secret")
    api.on("GET", "/sapi/v1/capital/deposit/hisrec", DEPOSITS)
    api.on("GET", "/sapi/v1/capital/withdraw/history", WITHDRAWALS)
    observed = {
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits(symbol="BTC", start_time=SEP_1, limit=2)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(
            api, lambda: client.get_withdrawals(symbol="BTC", start_time=SEP_1, limit=3)
        ),
    }
    _reset(api)
    api.on("GET", "/sapi/v1/capital/deposit/hisrec", INVALID_KEY, status=401)
    api.on("GET", "/sapi/v1/capital/withdraw/history", INVALID_KEY, status=401)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)
    assert_golden("binance_transfers", observed)


def _trade(symbol: str, trade_id: int, is_buyer: bool, ts: int, **extra: Any) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "id": trade_id,
        "orderId": trade_id * 10,
        "price": "60000.5",
        "qty": "0.01",
        "quoteQty": "600.005",
        "commission": "0.00001",
        "commissionAsset": "BNB",
        "time": ts,
        "isBuyer": is_buyer,
        "isMaker": False,
        "isBestMatch": True,
        **extra,
    }


PAIRS = {
    "symbols": [
        {"symbol": s, "status": "TRADING"}
        for s in ("BTCUSDT", "BTCEUR", "BTCUSDC", "ETHUSDT", "USDCUSDT", "EURUSDT", "SOLUSDT")
    ]
    + [{"symbol": "ETHBTC", "status": "BREAK"}]
}
TRADES = {
    "BTCUSDT": [_trade("BTCUSDT", 1, True, T0), _trade("BTCUSDT", 2, False, T0 + 60_000)],
    "BTCEUR": [_trade("BTCEUR", 3, True, T0 + 120_000, price="55000", commissionAsset="EUR")],
    "ETHUSDT": [
        _trade("ETHUSDT", 4, False, T0 + 180_000, price="2500.25"),
        _without(_trade("ETHUSDT", 5, True, T0 + 240_000), "qty"),
    ],
}


def _my_trades(request: httpx.Request) -> list[dict[str, Any]]:
    symbol = _param(request, "symbol")
    if symbol == "SOLUSDT" and _param(request, "fromId") == "1001":
        return [_trade("SOLUSDT", 1001, False, T0 + 1_001_000)]
    if symbol == "SOLUSDT":
        return [_trade("SOLUSDT", i, i % 2 == 0, T0 + i * 1000) for i in range(1, 1001)]
    return TRADES.get(symbol, [])


async def test_binance_trades_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, *MODULES)
    _reset(api)
    api.on("GET", "/api/v3/exchangeInfo", PAIRS)
    api.on(
        "GET",
        "/api/v3/account",
        {"balances": [_balance(asset, "1") for asset in ("BTC", "ETH", "EUR", "USDT", "USDC", "DOGE")]},
    )
    api.on("GET", "/api/v3/myTrades", _my_trades)
    client = BinanceService("key", "secret")
    observed = {
        "all_symbols": await record(api, client.get_trades),
        "single_symbol_window": await record(
            api, lambda: client.get_trades(symbol="BTC", start_time=SEP_1, end_time=OCT_1)
        ),
        "limit_reached": await record(api, lambda: client.get_trades(symbol="BTC", limit=2)),
        "paginated": await record(
            api, lambda: _summary(client.get_trades(symbol="SOL", start_time=SEP_1, end_time=OCT_1, limit=1001))
        ),
        "unknown_symbol": await record(api, lambda: client.get_trades(symbol="NOPE")),
    }
    api.scripts.pop(("GET", "/api/v3/myTrades"))
    api.on("GET", "/api/v3/myTrades", {"code": -1021, "msg": "Timestamp outside recvWindow."}, status=400)
    observed["symbol_refused"] = await record(api, lambda: client.get_trades(symbol="BTC"))

    _reset(api)
    api.on("GET", "/api/v3/exchangeInfo", {"code": 0, "msg": "busy"}, status=503)
    api.on("GET", "/api/v3/account", INVALID_KEY, status=401)
    observed["account_refused"] = await record(api, BinanceService("key", "secret").get_trades)
    assert_golden("binance_trades", observed)


def _fiat(status: str, source: str, obtain: str, ts: int, **extra: Any) -> dict[str, Any]:
    return {
        "sourceAmount": source,
        "fiatCurrency": "EUR",
        "obtainAmount": obtain,
        "cryptoCurrency": "BTC",
        "totalFee": "1.5",
        "price": "0",
        "status": status,
        "paymentMethod": "Card",
        "createTime": ts,
        "updateTime": ts,
        **extra,
    }


FIAT_PAGES = {
    ("0", False, "1"): [_fiat("Failed", "10", "0.0001", T0 - i * 1000, orderNo=f"x{i}") for i in range(498)]
    + [
        _fiat("Completed", "100", "0.0015", T0, orderNo="b1", fiatCurrency="USD"),
        _without(_fiat("Completed", "50", "0.02", T0 + 1000, cryptoCurrency="ETH"), "fiatCurrency"),
    ],
    ("0", False, "2"): [
        _fiat("Completed", "20", "0.0003", T0 + 2000, orderNo="b3"),
        _fiat("Processing", "30", "0.0004", T0 + 2500, orderNo="b4"),
    ],
    ("1", True, "1"): [
        _fiat("Completed", "0.01", "600", T0 + 3000, orderNo="s1"),
        _fiat("Completed", "0", "10", T0 + 4000, orderNo="s2"),
    ],
}


def _fiat_payments(request: httpx.Request) -> dict[str, Any]:
    oldest_chunk = _param(request, "beginTime") == str(_ms(JUN_1))
    key = (_param(request, "transactionType"), oldest_chunk, _param(request, "page"))
    return {"code": "000000", "message": "success", "data": FIAT_PAGES.get(key, []), "total": 0, "success": True}


def _conversion(from_asset: str, from_amount: str, to_asset: str, to_amount: str, ts: int) -> dict[str, Any]:
    return {
        "quoteId": f"q{ts}",
        "orderId": ts,
        "orderStatus": "SUCCESS",
        "fromAsset": from_asset,
        "fromAmount": from_amount,
        "toAsset": to_asset,
        "toAmount": to_amount,
        "ratio": "0",
        "inverseRatio": "0",
        "createTime": ts,
    }


CONVERSIONS = [
    _conversion("EUR", "100", "BTC", "0.0015", T0),
    _conversion("BTC", "0.01", "EUR", "600", T0 + 1000),
    _conversion("USDT", "50", "BTC", "0.0008", T0 + 2000),
    _conversion("BTC", "0.02", "USDT", "1200", T0 + 3000),
    _conversion("USDC", "100", "ETH", "0.04", T0 + 4000),
    _conversion("ETH", "1", "SOL", "15.5", T0 + 5000),
    _conversion("EUR", "10", "USD", "11", T0 + 6000),
    _without(_conversion("GBP", "20", "ETH", "0", T0 + 7000), "quoteId"),
    _without(_conversion("ADA", "0", "DOT", "5", T0 + 8000), "quoteId"),
    _conversion("CAD", "30", "BTC", "0.0003", T0 + 9000),
    _conversion("BTC", "0.001", "AUD", "90", T0 + 10_000),
]


def _invest(status: str, executed: str, ts: int, **extra: Any) -> dict[str, Any]:
    return {
        "targetAsset": "BTC",
        "sourceAsset": "EUR",
        "executedAmount": executed,
        "sourceAssetAmount": "50",
        "status": status,
        "transactionTime": ts,
        **extra,
    }


DOCUMENTED_INVEST = {
    "id": 504,
    "targetAsset": "BTC",
    "planType": "SINGLE",
    "planName": "BTC plan",
    "planId": 1,
    "transactionDateTime": T0 + 4000,
    "transactionStatus": "SUCCESS",
    "failedType": "NONE",
    "sourceAsset": "USDT",
    "sourceAssetAmount": "100",
    "targetAssetAmount": "0.0016",
    "sourceWallet": "SPOT_WALLET",
    "flexibleUsed": "0",
    "transactionFee": "0.1",
    "transactionFeeUnit": "USDT",
    "executionPrice": "62500",
    "executionType": "RECURRING",
    "subscriptionCycle": "DAILY",
}
INVEST_FIRST_PAGE = [_invest("FAILURE", "0", T0 - i * 1000, id=i) for i in range(1, 96)] + [
    _invest("SUCCESS", "0.0008", T0, id=500),
    _without(_invest("SUCCESS", "0.02", T0 + 1000, targetAsset="ETH"), "sourceAsset"),
    _invest("SUCCESS", "0", T0 + 2000, id=502),
    _invest("PENDING", "0.001", T0 + 3000, id=503),
    DOCUMENTED_INVEST,
]


async def test_binance_conversions_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, *MODULES)
    _reset(api)
    client = BinanceService("key", "secret")
    api.on("GET", "/sapi/v1/fiat/payments", _fiat_payments)
    observed = {
        "fiat_orders_window": await record(api, lambda: client.get_fiat_orders(start_time=JUN_1, end_time=OCT_1)),
    }
    _reset(api)
    api.on("GET", "/sapi/v1/fiat/payments", {"code": "-1", "msg": "busy"}, status=500)
    observed["fiat_orders_default_range_refused"] = await record(api, client.get_fiat_orders)
    observed["fiat_orders_aware_start_only"] = await record(api, lambda: client.get_fiat_orders(start_time=JUN_1))

    _reset(api)
    api.on("GET", TRADE_FLOW, {"list": CONVERSIONS, "limit": 1000, "moreData": False})
    observed["convert_history_window"] = await record(
        api, lambda: client.get_convert_history(start_time=SEP_1, end_time=OCT_1)
    )
    observed["crypto_conversions_window"] = await record(
        api, lambda: client.get_crypto_conversions(start_time=SEP_1, end_time=OCT_1)
    )

    _reset(api)
    api.on(
        "GET",
        TRADE_FLOW,
        {"list": [_conversion("BTC", "0.001", "ETH", "0.02", T0 - i * 1000) for i in range(1000)], "moreData": True},
        {"list": [_conversion("EUR", "25", "SOL", "0.2", T0 - 2_000_000)], "moreData": False},
    )
    observed["convert_history_paginated"] = await record(
        api, lambda: client.get_convert_history(start_time=SEP_1, end_time=OCT_1, limit=1001)
    )

    _reset(api)
    api.on("GET", TRADE_FLOW, TOO_MANY, status=429)
    observed["convert_history_refused"] = await record(
        api, lambda: client.get_convert_history(start_time=SEP_1, end_time=OCT_1)
    )

    _reset(api)
    api.on("GET", TRADE_FLOW, TOO_MANY, status=429)
    api.on(
        "GET",
        TRADE_FLOW,
        {"list": [_conversion("BTC", "oops", "ETH", "1", T0)]},
        {"list": [_conversion("DOT", "10", "ATOM", "8", T0 - 40 * DAY_MS)]},
    )
    observed["crypto_conversions_resilient"] = await record(
        api, lambda: client.get_crypto_conversions(start_time=AUG_1, end_time=OCT_1)
    )

    _reset(api)
    api.on("GET", TRADE_FLOW, {"list": [], "moreData": False})
    observed["convert_history_default_range"] = await record(api, client.get_convert_history)
    observed["crypto_conversions_default_range"] = await record(api, client.get_crypto_conversions)
    observed["crypto_conversions_aware_start_only"] = await record(
        api, lambda: client.get_crypto_conversions(start_time=SEP_1)
    )

    _reset(api)
    api.on(
        "GET",
        AUTO_INVEST,
        {"list": INVEST_FIRST_PAGE, "total": 101},
        {"list": [_invest("SUCCESS", "0.001", T0 + 5000, id=600, sourceAsset="USDC")], "total": 101},
    )
    observed["auto_invest_paginated"] = await record(
        api, lambda: client.get_auto_invest_history(start_time=SEP_1, end_time=OCT_1)
    )
    _reset(api)
    api.on("GET", AUTO_INVEST, {"list": INVEST_FIRST_PAGE, "total": 101})
    observed["auto_invest_limit_reached"] = await record(api, lambda: client.get_auto_invest_history(limit=1))
    _reset(api)
    api.on("GET", AUTO_INVEST, INVALID_KEY, status=401)
    observed["auto_invest_refused"] = await record(api, client.get_auto_invest_history)
    assert_golden("binance_conversions", observed)


def _reward(asset: str, rewards: str, ts: int, reward_type: str) -> dict[str, Any]:
    return {"asset": asset, "rewards": rewards, "projectId": f"{asset}001", "type": reward_type, "time": ts}


RewardTable = dict[tuple[str, bool, str], tuple[list[dict[str, Any]], int]]

FLEXIBLE_ROWS: RewardTable = {
    ("REALTIME", True, "1"): (
        [
            _reward("BTC", "0.0001", T0, "REALTIME"),
            _reward("ETH", "0", T0 + 1000, "REALTIME"),
            _reward("", "1", T0 + 2000, "REALTIME"),
        ],
        150,
    ),
    ("REALTIME", True, "2"): ([_reward("BTC", "0.0002", T0 + 3000, "REALTIME")], 150),
    ("REALTIME", False, "1"): (
        [
            _reward("BTC", "0.0001", T0, "REALTIME"),
            _reward("ETH", "0.003", T0 - 20 * DAY_MS, "REALTIME"),
        ],
        2,
    ),
    ("BONUS", True, "1"): ([_reward("BNB", "0.01", T0 + 4000, "BONUS")], 1),
}
LOCKED_ROWS: RewardTable = {("REWARDS", False, "1"): ([_reward("DOT", "0.5", T0 - 25 * DAY_MS, "REWARDS")], 1)}


def _rewards(table: RewardTable) -> Callable[[httpx.Request], Any]:
    def respond(request: httpx.Request) -> dict[str, Any]:
        recent = _param(request, "startTime") == str(RECENT_REWARDS_START)
        rows, total = table.get((_param(request, "type"), recent, _param(request, "current")), ([], 0))
        return {"rows": rows, "total": total}

    return respond


async def test_binance_rewards_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, *MODULES)
    _reset(api)
    client = BinanceService("key", "secret")
    api.on("GET", FLEXIBLE_REWARDS, _rewards(FLEXIBLE_ROWS))
    api.on("GET", LOCKED_REWARDS, _rewards(LOCKED_ROWS))
    observed = {
        "rewards_recent_limit_ignored": await record(api, lambda: client.get_rewards(limit=1, lookback_days=40)),
    }
    api.scripts.pop(("GET", LOCKED_REWARDS))
    api.on("GET", LOCKED_REWARDS, {"code": -1002, "msg": "unauthorized"}, status=401)
    observed["rewards_locked_refused"] = await record(api, lambda: client.get_rewards(lookback_days=40))
    _reset(api)
    observed["rewards_default_lookback_unavailable"] = await record(api, lambda: client.get_rewards(start_time=SEP_1))
    assert_golden("binance_rewards", observed)
