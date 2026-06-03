"""Golden numeric tests for XIRR cashflow construction (FIN-02 / audit F-02..F-04, F-08).

These pin the pure pipeline ``_build_xirr_cashflows`` + ``_xirr`` against known
reference series, the gap the audit flagged: prior tests only checked XIRR was
"finite and within [-95, 1000]", never a value against a hand-computed expectation.

Covered:
  * #2 known cashflows -> known rate (10k in, 11k out one year -> ~10%)
  * #3 matched internal transfers must NOT move the rate (F-03)
  * #4 dividends/interest are counted as inflows (F-04)
  * per-line FX conversion via conversion_rate (F-02)
  * sign convention negative=outflow (F-08)
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.models.transaction import TransactionType
from app.services.analytics_service import _build_xirr_cashflows, _xirr


class _Tx:
    """Minimal stand-in for a Transaction row (only fields the helper reads)."""

    def __init__(self, ttype, qty, price, when, *, rate=None, fee=0):
        self.transaction_type = ttype
        self.quantity = Decimal(str(qty))
        self.price = Decimal(str(price))
        self.fee = Decimal(str(fee))
        self.conversion_rate = Decimal(str(rate)) if rate is not None else None
        self.executed_at = when


_T0 = datetime(2023, 1, 1, tzinfo=timezone.utc)
_T1 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_known_cashflows_yield_known_rate():
    """10 000 invested, 11 000 returned exactly one year later -> ~10% XIRR."""
    txs = [
        _Tx(TransactionType.BUY, qty=1, price=10000, when=_T0),
        _Tx(TransactionType.SELL, qty=1, price=11000, when=_T1),
    ]
    cashflows, skipped = _build_xirr_cashflows(txs)
    assert skipped == 0
    assert cashflows[0][1] < 0  # F-08: BUY is a negative (outflow)
    assert cashflows[1][1] > 0
    rate = _xirr(cashflows)
    assert rate is not None
    assert abs(rate * 100 - 10.0) < 0.1


def test_matched_internal_transfers_do_not_affect_rate():
    """A transfer_in/out pair (wallet hop) must be excluded entirely (F-03)."""
    base = [
        _Tx(TransactionType.BUY, qty=1, price=10000, when=_T0),
        _Tx(TransactionType.SELL, qty=1, price=11000, when=_T1),
    ]
    with_transfers = base + [
        _Tx(TransactionType.TRANSFER_OUT, qty=1, price=10500, when=datetime(2023, 6, 1, tzinfo=timezone.utc)),
        _Tx(TransactionType.TRANSFER_IN, qty=1, price=10500, when=datetime(2023, 6, 1, tzinfo=timezone.utc)),
    ]
    cf_base, _ = _build_xirr_cashflows(base)
    cf_xfer, _ = _build_xirr_cashflows(with_transfers)
    # Transfers contribute zero extra cashflows.
    assert len(cf_xfer) == len(cf_base)
    assert _xirr(cf_xfer) == _xirr(cf_base)


def test_dividends_and_interest_count_as_inflows():
    """DIVIDEND and INTEREST are positive inflows (F-04), raising the rate."""
    without = [
        _Tx(TransactionType.BUY, qty=1, price=10000, when=_T0),
        _Tx(TransactionType.SELL, qty=1, price=10000, when=_T1),
    ]
    with_income = without + [
        _Tx(TransactionType.DIVIDEND, qty=1, price=300, when=datetime(2023, 7, 1, tzinfo=timezone.utc)),
        _Tx(TransactionType.INTEREST, qty=1, price=200, when=datetime(2023, 7, 1, tzinfo=timezone.utc)),
    ]
    cf_without, _ = _build_xirr_cashflows(without)
    cf_with, _ = _build_xirr_cashflows(with_income)
    assert len(cf_with) == len(cf_without) + 2
    # Flat trade returns ~0%; adding 500 of income makes it strictly positive.
    assert (_xirr(cf_without) or 0) < (_xirr(cf_with) or 0)


def test_per_line_conversion_rate_applied():
    """A USD buy with conversion_rate 0.9 contributes -9000 EUR, not -10000 (F-02)."""
    txs = [_Tx(TransactionType.BUY, qty=1, price=10000, when=_T0, rate="0.9")]
    cashflows, _ = _build_xirr_cashflows(txs)
    assert cashflows[0][1] == -9000.0


def test_eur_to_target_scales_all_lines():
    """A non-EUR view multiplies every EUR amount by eur_to_target."""
    txs = [
        _Tx(TransactionType.BUY, qty=1, price=1000, when=_T0),
        _Tx(TransactionType.SELL, qty=1, price=2000, when=_T1),
    ]
    cf_eur, _ = _build_xirr_cashflows(txs, eur_to_target=1.0)
    cf_usd, _ = _build_xirr_cashflows(txs, eur_to_target=1.1)
    assert cf_usd[0][1] == cf_eur[0][1] * 1.1
    assert cf_usd[1][1] == cf_eur[1][1] * 1.1
    # A uniform scale of all flows leaves the rate unchanged.
    assert abs((_xirr(cf_usd) or 0) - (_xirr(cf_eur) or 0)) < 1e-6


def test_null_date_rows_are_skipped():
    txs = [
        _Tx(TransactionType.BUY, qty=1, price=100, when=None),
        _Tx(TransactionType.BUY, qty=1, price=100, when=_T0),
    ]
    cashflows, skipped = _build_xirr_cashflows(txs)
    assert skipped == 1
    assert len(cashflows) == 1
