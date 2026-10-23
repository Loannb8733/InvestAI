from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

import app.services.exchanges.kraken as module
from app.services.exchanges.kraken import KrakenService
from tests.exchanges.clients.harness import assert_golden, install, record

SECRET = "c2VjcmV0"
REFUSED = {"error": ["EAPI:Invalid key"]}
START = datetime(2023, 11, 1, tzinfo=UTC)
END = datetime(2023, 12, 1, tzinfo=UTC)


def _ok(result: Any) -> dict[str, Any]:
    return {"error": [], "result": result}


def _offset(request: httpx.Request) -> int:
    return int(dict(parse_qsl(request.content.decode()))["ofs"])


def _pages(pages: dict[int, Any]) -> Callable[[httpx.Request], Any]:
    return lambda request: pages.get(_offset(request), _ok({}))


def _ids(call: Callable[[], Awaitable[list[Any]]], field: str) -> Callable[[], Awaitable[list[str]]]:
    async def run() -> list[str]:
        return [item[field] if isinstance(item, dict) else getattr(item, field) for item in await call()]

    return run


def _trade(pair: str, side: str, vol: str, price: str, fee: str, time: float) -> dict[str, Any]:
    return {
        "ordertxid": "OQCLML-BW3P3-BUCMWZ",
        "pair": pair,
        "time": time,
        "type": side,
        "ordertype": "limit",
        "price": price,
        "cost": "0",
        "fee": fee,
        "vol": vol,
    }


def _entry(
    refid: str, kind: str, asset: str, amount: str, time: float, fee: str = "0", subtype: str = ""
) -> dict[str, Any]:
    return {
        "refid": refid,
        "time": time,
        "type": kind,
        "subtype": subtype,
        "aclass": "currency",
        "asset": asset,
        "amount": amount,
        "fee": fee,
        "balance": "10",
    }


def _trade_page(start: int, count: int) -> dict[str, Any]:
    return {
        f"TP{i:03d}": _trade("XXBTZEUR", "buy", "0.001", "30000", "0.01", 1690000000 + i)
        for i in range(start, start + count)
    }


def _ledger_page(start: int, count: int) -> dict[str, Any]:
    return {
        f"LP{i:03d}": _entry(f"RP{i:03d}", "staking", "DOT.S", "0.01", 1690000000 + i)
        for i in range(start, start + count)
    }


LEDGER = {
    "L01": _entry("RBUY", "spend", "ZEUR", "-100.0000", 1700000000.25, fee="0.9000"),
    "L02": _entry("RBUY", "receive", "XXBT", "0.0025000000", 1700000000.25),
    "L03": _entry("RMULTI", "spend", "ZEUR", "-1.5000", 1700000100),
    "L04": _entry("RMULTI", "spend", "ZEUR", "-250.0000", 1700000100, fee="2.5000"),
    "L05": _entry("RMULTI", "receive", "XETH", "0.1000000000", 1700000100),
    "L06": _entry("RMULTI", "receive", "XETH", "0.0010000000", 1700000100),
    "L07": _entry("RTRADE", "trade", "ZUSD", "-60.0000", 1700000200, fee="0.1000"),
    "L08": _entry("RTRADE", "trade", "SOL", "0.5000000000", 1700000200),
    "L09": _entry("RSELL", "trade", "XXBT", "-0.0100000000", 1700000300),
    "L10": _entry("RSELL", "trade", "ZEUR", "500.0000", 1700000300, fee="0.8000"),
    "L11": _entry("RCONV", "spend", "XXBT", "-0.0100000000", 1700000400, fee="0.0000100000"),
    "L12": _entry("RCONV", "receive", "DOT", "25.0000000000", 1700000400, fee="0.0100000000"),
    "L13": _entry("RMIX", "spend", "ZEUR", "-100.0000", 1700000500),
    "L14": _entry("RMIX", "receive", "XXDG", "1000.00000000", 1700000500),
    "L15": _entry("RMIX", "spend", "XETH", "-0.0300000000", 1700000500),
    "L16": _entry("RZERO", "spend", "ZGBP", "-10.0000", 1700000600),
    "L17": _entry("RZERO", "receive", "XXRP", "0.00000000", 1700000600),
    "L18": _entry("RTWOSELLS", "spend", "XETH", "-0.5000000000", 1700000700),
    "L19": _entry("RTWOSELLS", "spend", "XETH", "-0.0200000000", 1700000700),
    "L20": _entry("RTWOSELLS", "receive", "USDC", "1200.00000000", 1700000700),
    "L21": _entry("RSTAKE", "staking", "DOT.S", "0.1200000000", 1700000800),
    "L22": _entry("REARN", "earn", "ETH2.S", "0.0030000000", 1700000900, subtype="autoallocation"),
    "L23": _entry("RDROP", "transfer", "FLR", "40.0000", 1700001000, subtype="Airdrop"),
    "L24": _entry("RBONUS", "bonus", "XXBT", "0.0000500000", 1700001100),
    "L25": _entry("RCREDIT", "credit", "SOL.F", "0.0200000000", 1700001200),
    "L26": _entry("RFIATREWARD", "staking", "ZEUR", "0.5000", 1700001300),
    "L27": _entry("RCHF", "staking", "ZCHF", "0.2000", 1700001400),
    "L28": _entry("RUNSTAKE", "staking", "DOT.S", "-0.1200000000", 1700001500),
    "L29": _entry("RMOVE", "transfer", "DOT", "1.0000000000", 1700001600, subtype="spottostaking"),
    "L30": _entry("", "deposit", "ZEUR", "1000.0000", 1700001700),
    "L31": _entry("RWITHDRAW", "withdrawal", "XXBT", "-0.1000000000", 1700001800, fee="0.0001000000"),
    "L32": {"time": 1700001900, "type": "adjustment", "asset": "XXLM", "amount": "5.0000", "fee": "0", "balance": "5"},
}


async def test_kraken_account_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = KrakenService("key", SECRET)
    api.on(
        "POST",
        "/0/private/Balance",
        _ok(
            {
                "XXBT": "0.5000000000",
                "ZEUR": "1250.4300",
                "ETH2.S": "1.2000000000",
                "SOL.F": "3.0000000000",
                "ADA.S": "100.00000000",
                "XXDG": "10.00000000",
                "XMLN": "2.0000000000",
                "KFEE": "0.00",
                "USDT": "0.00000000",
            }
        ),
    )
    api.on(
        "POST",
        "/0/private/DepositStatus",
        _ok(
            [
                {
                    "method": "SEPA",
                    "aclass": "currency",
                    "asset": "ZEUR",
                    "refid": "D1",
                    "txid": "TX1",
                    "info": "IBAN",
                    "amount": "500.0000",
                    "fee": "0.0000",
                    "time": 1700000000,
                    "status": "Success",
                },
                {"asset": "XXBT", "amount": "0.0500000000", "time": 1700001000, "status": "Settled"},
                {
                    "asset": "ADA",
                    "refid": "D3",
                    "txid": "TX3",
                    "amount": "100.0000",
                    "time": 1699000000,
                    "status": "Failure",
                },
            ]
        ),
    )
    api.on(
        "POST",
        "/0/private/WithdrawStatus",
        _ok(
            [
                {
                    "method": "Ether",
                    "aclass": "currency",
                    "asset": "XETH",
                    "refid": "W1",
                    "txid": "0xabc",
                    "info": "0xdef",
                    "amount": "0.5000000000",
                    "fee": "0.0035000000",
                    "time": 1700002000,
                    "status": "Success",
                },
                {"asset": "DOT", "amount": "12.0000000000", "time": 1700003000, "status": "Pending"},
            ]
        ),
    )
    observed = {
        "test_connection": await record(api, client.test_connection),
        "balances": await record(api, client.get_balances),
        "deposits": await record(api, client.get_deposits),
        "deposits_filtered": await record(api, lambda: client.get_deposits(symbol="XBT", limit=1)),
        "withdrawals": await record(api, client.get_withdrawals),
        "withdrawals_filtered": await record(api, lambda: client.get_withdrawals(symbol="ETH", limit=1)),
    }
    api.scripts.clear()
    api.on("POST", "/0/private/Balance", _ok({}))
    api.on("POST", "/0/private/DepositStatus", _ok([]))
    api.on("POST", "/0/private/WithdrawStatus", _ok([]))
    observed["balances_empty"] = await record(api, client.get_balances)
    observed["deposits_empty"] = await record(api, client.get_deposits)
    observed["withdrawals_empty"] = await record(api, client.get_withdrawals)
    api.scripts.clear()
    for path in ("/0/private/Balance", "/0/private/DepositStatus", "/0/private/WithdrawStatus"):
        api.on("POST", path, REFUSED)
    observed["connection_refused"] = await record(api, client.test_connection)
    observed["balances_refused"] = await record(api, client.get_balances)
    observed["deposits_refused"] = await record(api, client.get_deposits)
    observed["withdrawals_refused"] = await record(api, client.get_withdrawals)
    api.scripts.clear()
    api.on("POST", "/0/private/Balance", _ok({"XXBT": "1"}), status=500)
    observed["connection_http_error"] = await record(api, client.test_connection)
    observed["balances_http_error"] = await record(api, client.get_balances)
    keyless = KrakenService("key")
    observed["connection_without_secret"] = await record(api, keyless.test_connection)
    observed["balances_without_secret"] = await record(api, keyless.get_balances)
    assert_golden("kraken_account", observed)


async def test_kraken_trades_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = KrakenService("key", SECRET)
    api.on(
        "POST",
        "/0/private/TradesHistory",
        _ok(
            {
                "count": 5,
                "trades": {
                    "T1": _trade("XXBTZEUR", "buy", "0.0100000000", "30000.0", "0.48000", 1700000000.1234),
                    "T2": _trade("ETHXBT", "sell", "1.0000000000", "0.05500", "0.00010", 1700000500),
                    "T3": _trade("SOLUSDT", "buy", "10.00000000", "60.00", "0.90000", 1699990000),
                    "T4": _trade("DOTJPY", "buy", "5.00000000", "900.0", "7.00000", 1700001000),
                    "T5": _trade("XXLMXXBT", "sell", "300.00000000", "0.0000030", "0.0000020", 1700000250),
                },
            }
        ),
    )
    observed = {
        "trades": await record(api, client.get_trades),
        "trades_windowed": await record(
            api, lambda: client.get_trades(symbol="XXBTZEUR", start_time=START, end_time=END, limit=2)
        ),
    }
    api.scripts.clear()
    api.on(
        "POST",
        "/0/private/TradesHistory",
        _pages(
            {
                0: _ok({"count": 53, "trades": _trade_page(0, 50)}),
                50: _ok({"count": 53, "trades": _trade_page(50, 3)}),
            }
        ),
    )
    observed["trades_paginated"] = await record(api, _ids(client.get_trades, "trade_id"))
    observed["trades_capped_by_limit"] = await record(api, _ids(lambda: client.get_trades(limit=20), "trade_id"))
    api.scripts.clear()
    interrupted = {0: _ok({"count": 99, "trades": _trade_page(0, 50)}), 50: REFUSED}
    api.on("POST", "/0/private/TradesHistory", _pages(interrupted))
    observed["trades_refused_mid_pagination"] = await record(api, _ids(client.get_trades, "trade_id"))
    api.scripts.clear()
    api.on("POST", "/0/private/TradesHistory", _ok({"count": 0, "trades": {}}))
    observed["trades_empty"] = await record(api, client.get_trades)
    api.scripts.clear()
    api.on("POST", "/0/private/TradesHistory", REFUSED)
    observed["trades_refused"] = await record(api, client.get_trades)
    assert_golden("kraken_trades", observed)


async def test_kraken_ledgers_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = KrakenService("key", SECRET)
    api.on("POST", "/0/private/Ledgers", _ok({"count": len(LEDGER), "ledger": LEDGER}))
    observed = {
        "ledgers": await record(api, client.get_ledgers),
        "ledgers_filtered": await record(
            api,
            _ids(
                lambda: client.get_ledgers(asset="XBT", ledger_type="trade", start_time=START, end_time=END, limit=3),
                "ledger_id",
            ),
        ),
    }
    api.scripts.clear()
    api.on(
        "POST",
        "/0/private/Ledgers",
        _pages(
            {
                0: _ok({"count": 100, "ledger": _ledger_page(0, 50)}),
                50: _ok({"count": 100, "ledger": _ledger_page(50, 50)}),
            }
        ),
    )
    observed["ledgers_paginated"] = await record(api, _ids(client.get_ledgers, "ledger_id"))
    observed["ledgers_capped_by_limit"] = await record(api, _ids(lambda: client.get_ledgers(limit=60), "ledger_id"))
    api.scripts.clear()
    api.on("POST", "/0/private/Ledgers", _pages({0: _ok({"count": 99, "ledger": _ledger_page(0, 50)}), 50: REFUSED}))
    observed["ledgers_refused_mid_pagination"] = await record(api, _ids(client.get_ledgers, "ledger_id"))
    api.scripts.clear()
    api.on("POST", "/0/private/Ledgers", _ok({"count": 0, "ledger": {}}))
    observed["ledgers_empty"] = await record(api, client.get_ledgers)
    api.scripts.clear()
    api.on("POST", "/0/private/Ledgers", REFUSED)
    observed["ledgers_refused"] = await record(api, client.get_ledgers)
    assert_golden("kraken_ledgers", observed)


async def test_kraken_ledger_derived_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, module)
    client = KrakenService("key", SECRET)
    api.on("POST", "/0/private/Ledgers", _ok({"count": len(LEDGER), "ledger": LEDGER}))
    ledgers = await client.get_ledgers()
    _, instant_refids = await client.get_instant_buys(ledgers=ledgers)
    observed = {
        "instant_buys": await record(api, client.get_instant_buys),
        "instant_buys_truncated": await record(api, lambda: client.get_instant_buys(limit=2)),
        "instant_buys_prefetched": await record(api, lambda: client.get_instant_buys(ledgers=ledgers)),
        "conversions": await record(api, client.get_crypto_conversions),
        "conversions_truncated": await record(api, lambda: client.get_crypto_conversions(limit=6)),
        "conversions_prefetched": await record(api, lambda: client.get_crypto_conversions(ledgers=ledgers)),
        "conversions_excluding_instant_buys": await record(
            api, lambda: client.get_crypto_conversions(exclude_refids=instant_refids, ledgers=ledgers)
        ),
        "rewards": await record(api, client.get_rewards),
        "rewards_truncated": await record(api, lambda: client.get_rewards(limit=24)),
        "rewards_prefetched": await record(api, lambda: client.get_rewards(ledgers=ledgers)),
    }
    api.scripts.clear()
    api.on("POST", "/0/private/Ledgers", REFUSED)
    observed["instant_buys_refused"] = await record(api, client.get_instant_buys)
    observed["conversions_refused"] = await record(api, client.get_crypto_conversions)
    observed["rewards_refused"] = await record(api, client.get_rewards)
    assert_golden("kraken_ledger_derived", observed)
