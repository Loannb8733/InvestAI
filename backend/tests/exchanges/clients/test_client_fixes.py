from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.domains.exchanges.connectors import bitpanda
from app.domains.exchanges.connectors.binance import conversions as binance_conversions
from app.domains.exchanges.connectors.binance import core as binance_core
from app.domains.exchanges.connectors.binance import earn as binance_earn
from app.domains.exchanges.connectors.binance import fiat as binance_fiat
from app.domains.exchanges.connectors.binance.connector import BinanceService
from app.domains.exchanges.connectors.bitpanda import BitpandaService
from app.domains.exchanges.connectors.bitstamp import movements as bitstamp_movements
from app.domains.exchanges.connectors.bitstamp import trades as bitstamp_trades
from app.domains.exchanges.connectors.bitstamp.connector import BitstampService
from app.domains.exchanges.connectors.bybit import trades as bybit_trades
from app.domains.exchanges.connectors.bybit.connector import BybitService
from tests.exchanges.clients.harness import install

BINANCE_MODULES = (binance_core, binance_fiat, binance_conversions, binance_earn)


def _binance(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, BinanceService]:
    api = install(monkeypatch, *BINANCE_MODULES)
    api.on("GET", "/api/v3/time", {"serverTime": 1790000000000})
    return api, BinanceService("key", "secret")


async def test_a_bitstamp_rate_key_is_not_taken_for_a_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, bitstamp_trades, bitstamp_movements)
    row = {
        "id": 7,
        "type": "2",
        "datetime": "2025-03-10 12:00:00",
        "btc": "0.01",
        "usd": "-370.00",
        "btc_usd": "37000.00",
        "fee": "0.9",
    }
    api.on("POST", "/api/v2/user_transactions/", [row])
    trades = await BitstampService("key", "secret").get_trades()
    assert [(t.symbol, t.side, t.quantity, t.price) for t in trades] == [
        ("BTC_USD", "buy", Decimal("0.01"), Decimal("37000"))
    ]


async def test_bitpanda_balances_are_read_inside_their_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, bitpanda)
    balance = {"currency_code": "BTC", "available": "0.5", "locked": "0.1"}
    api.on("GET", "/api/v1/account/balances", {"account_id": "acc", "balances": [balance]})
    balances = await BitpandaService("key").get_balances()
    assert [(b.symbol, b.total) for b in balances] == [("BTC", Decimal("0.6"))]


async def test_binance_auto_invest_reads_the_documented_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    api, client = _binance(monkeypatch)
    row = {
        "id": 382213,
        "targetAsset": "BTC",
        "transactionDateTime": 1741608000000,
        "transactionStatus": "SUCCESS",
        "sourceAsset": "EUR",
        "sourceAssetAmount": "100",
        "targetAssetAmount": "0.002",
        "transactionFee": "0.1",
        "transactionFeeUnit": "EUR",
    }
    failed = {**row, "id": 382214, "transactionStatus": "FAILED"}
    api.on("GET", "/sapi/v1/lending/auto-invest/history/list", {"total": 2, "list": [row, failed]})
    orders = await client.get_auto_invest_history()
    assert [(o.order_id, o.crypto_amount, o.fiat_amount, o.price, o.fee, o.timestamp) for o in orders] == [
        (
            "autoinvest_382213",
            Decimal("0.002"),
            Decimal("100"),
            Decimal("50000"),
            Decimal("0.1"),
            datetime(2025, 3, 10, 12, 0, tzinfo=UTC),
        )
    ]


@pytest.mark.parametrize("method", ["get_fiat_orders", "get_crypto_conversions"])
async def test_binance_history_accepts_an_aware_start_alone(monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    api, client = _binance(monkeypatch)
    api.on("GET", "/sapi/v1/fiat/payments", {"code": "000000", "data": []})
    api.on("GET", "/sapi/v1/convert/tradeFlow", {"list": []})
    result = await getattr(client, method)(start_time=datetime(2026, 7, 1, tzinfo=UTC))
    assert result == []
    assert api.calls


async def test_bybit_trades_stop_at_the_limit_inside_a_page(monkeypatch: pytest.MonkeyPatch) -> None:
    api = install(monkeypatch, bybit_trades)
    fills = [
        {
            "execId": f"e{i}",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execQty": "0.01",
            "execPrice": "60000",
            "execFee": "0.1",
            "feeCurrency": "USDT",
            "execTime": str(1741608000000 + i),
        }
        for i in range(4)
    ]
    api.on("GET", "/v5/execution/list", {"retCode": 0, "result": {"list": fills, "nextPageCursor": "next"}})
    trades = await BybitService("key", "secret").get_trades(limit=3)
    assert len(trades) == 3
