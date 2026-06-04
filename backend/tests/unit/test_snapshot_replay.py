"""Unit tests for snapshot replay metric fixes (Ticket 2).

2a: crypto→crypto conversions must be net_capital-NEUTRAL (a swap conserves
    invested capital; the sync gives CONVERSION_IN price=0, so the old code
    drained net_capital on every swap).
2b: same-day transactions apply IN/BUY before OUT/SELL so a same-timestamp
    OUT cannot clamp holdings to 0 before its matching IN.
"""

from datetime import datetime
from types import SimpleNamespace

from app.models.transaction import TransactionType
from app.services.snapshot_service import SnapshotService


def _tx(symbol, ttype, qty, price, when):
    return SimpleNamespace(
        symbol=symbol,
        transaction_type=ttype,
        quantity=qty,
        price=price,
        executed_at=when,
        created_at=when,
        asset_type="crypto",
    )


class TestConversionNeutrality:
    def test_swap_does_not_drain_net_capital(self):
        svc = SnapshotService()
        day1 = datetime(2026, 6, 1)
        day2 = datetime(2026, 6, 2)
        txs = [
            _tx("PEPE", TransactionType.BUY, 1000.0, 0.001, day1),  # invest 1.0
            # Swap PEPE -> PAXG on day2: OUT priced, IN price=0 (as the sync stores it)
            _tx("PEPE", TransactionType.CONVERSION_OUT, 1000.0, 0.001, day2),
            _tx("PAXG", TransactionType.CONVERSION_IN, 0.0003, 0.0, day2),
        ]
        _, _, daily_net_capital, _ = svc._replay_transactions_to_daily_holdings(txs, day1, day2)
        # Net capital after the swap must equal what it was before (≈1.0), not drained.
        assert abs(daily_net_capital["2026-06-01"] - 1.0) < 1e-9
        assert abs(daily_net_capital["2026-06-02"] - 1.0) < 1e-9


class TestIntradayOrdering:
    def test_in_applied_before_out_same_timestamp(self):
        svc = SnapshotService()
        day = datetime(2026, 6, 1)
        # Same timestamp: a SELL listed before the BUY that funds it.
        txs = [
            _tx("BTC", TransactionType.SELL, 1.0, 50000.0, day),
            _tx("BTC", TransactionType.BUY, 2.0, 50000.0, day),
        ]
        daily_holdings, _, _, _ = svc._replay_transactions_to_daily_holdings(txs, day, day)
        # IN-first → 2 bought then 1 sold = 1 held (not clamped to wrong value).
        assert abs(daily_holdings["2026-06-01"].get("BTC", 0.0) - 1.0) < 1e-9
