"""Golden numerical tests for the XIRR solver (FIN-TEST).

Background (audit 2026-06-03): the existing `tests/test_xirr_edge_cases.py` is an
HTTP integration test that only asserts the result is bounded in [-95, 1000] — it
verifies NO actual numeric value. These tests pin the *solver* (`_xirr`) to known
closed-form answers so a regression in the root-finder is caught deterministically,
with no DB / HTTP / Docker.

Scope: this file tests `_xirr` (the NPV root-finder), which the audit found to be
mathematically correct. The *cashflow construction* bugs (FIN-02: ignores
`tx.currency`, counts internal transfers, drops dividends/interest) live in
`compute_xirr` and are covered separately once that logic is extracted into a pure,
testable helper as part of the FIN-02 fix.

Sign convention used by `_xirr` cashflows in this suite: investment (outflow)
NEGATIVE, value/withdrawal (inflow) POSITIVE — i.e. NPV = sum(amt / (1+r)^t) = 0.
Note: IRR is invariant to a global sign flip, so the docstring's stated convention
(FIN-05, to be corrected) does not change these expected values.
"""

from datetime import datetime, timedelta

import pytest

from app.services.analytics_service import _xirr


def _years_later(d0: datetime, days: int) -> datetime:
    return d0 + timedelta(days=days)


class TestXirrGolden:
    """Closed-form XIRR cases with known answers."""

    def test_single_flow_returns_none(self):
        """Fewer than 2 cashflows → cannot compute a rate."""
        d0 = datetime(2024, 1, 1)
        assert _xirr([(d0, -10000.0)]) is None

    def test_empty_returns_none(self):
        assert _xirr([]) is None

    def test_ten_percent_one_year(self):
        """10 000 invested, worth 11 000 exactly one year later → ~10 %.

        Day-count is 365/365.25, so the exact root is ~10.007 %, not a clean 10 %.
        We assert tight tolerance around the analytic value.
        """
        d0 = datetime(2024, 1, 1)
        cashflows = [(d0, -10000.0), (_years_later(d0, 365), 11000.0)]
        r = _xirr(cashflows)
        assert r is not None
        assert r == pytest.approx(0.10, abs=2e-3)

    def test_doubling_one_year_is_100_percent(self):
        """10 000 → 20 000 in one year ≈ 100 %."""
        d0 = datetime(2024, 1, 1)
        r = _xirr([(d0, -10000.0), (_years_later(d0, 365), 20000.0)])
        assert r is not None
        assert r == pytest.approx(1.00, abs=3e-3)

    def test_flat_zero_return(self):
        """No gain over a year → ~0 %."""
        d0 = datetime(2024, 1, 1)
        r = _xirr([(d0, -10000.0), (_years_later(d0, 365), 10000.0)])
        assert r is not None
        assert r == pytest.approx(0.0, abs=1e-6)

    def test_loss_is_negative(self):
        """10 000 → 8 000 in one year ≈ -20 %."""
        d0 = datetime(2024, 1, 1)
        r = _xirr([(d0, -10000.0), (_years_later(d0, 365), 8000.0)])
        assert r is not None
        assert r == pytest.approx(-0.20, abs=3e-3)

    def test_sign_flip_invariance(self):
        """IRR is invariant to negating all cashflows (FIN-05 docstring is cosmetic)."""
        d0 = datetime(2024, 1, 1)
        cf = [(d0, -10000.0), (_years_later(d0, 365), 11000.0)]
        cf_flipped = [(d, -amt) for d, amt in cf]
        r1 = _xirr(cf)
        r2 = _xirr(cf_flipped)
        assert r1 is not None and r2 is not None
        assert r1 == pytest.approx(r2, abs=1e-9)

    def test_multi_flow_staggered_investments(self):
        """Two investments at different dates, single exit — root brackets cleanly.

        10 000 at t0, 5 000 at t0+182d, exit 17 000 at t0+365d.
        Verify the solved rate actually zeroes the NPV (self-consistency), since the
        closed form is awkward with mid-period flows.
        """
        d0 = datetime(2024, 1, 1)
        cashflows = [
            (d0, -10000.0),
            (_years_later(d0, 182), -5000.0),
            (_years_later(d0, 365), 17000.0),
        ]
        r = _xirr(cashflows)
        assert r is not None
        # Recompute NPV at the solved rate — must be ~0.
        npv = sum(amt / (1.0 + r) ** ((d - d0).days / 365.25) for d, amt in cashflows)
        assert npv == pytest.approx(0.0, abs=1e-4)
