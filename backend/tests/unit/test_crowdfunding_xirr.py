"""Golden tests for the crowdfunding realized-XIRR (``compute_xirr``).

``compute_xirr`` is the pure gateway used by /crowdfunding/performance : it
validates the dated flows (both signs present, span >= 30 days) then delegates
the root-finding to the shared solver ``app.services.analytics_math._xirr``
(Brent bisection on [-0.99, 10.0], Newton fallback, day-count 365.25).

Sign convention: negative = cash out (investment), positive = cash in
(repayment / terminal CRD value). Returns a decimal rate (0.10 = 10 %).

Convention on total defaults (documented here as the reference): a DEFAULTED
project with NO recorded repayment produces only the initial outflow — there
is no definable rate, so ``compute_xirr`` returns ``None``. A default with
partial recoveries yields a strongly NEGATIVE rate (the loss is measured).
"""

from datetime import date, timedelta

import pytest

from app.api.v1.endpoints.crowdfunding import compute_xirr

D0 = date(2024, 1, 1)


def _days(n: int) -> date:
    return D0 + timedelta(days=n)


class TestComputeXirrGolden:
    """Closed-form cases with known answers."""

    def test_in_fine_perfect_ten_percent(self):
        """-10 000 @ J0, +11 000 @ J+365 → ~10 % (10.007 % with 365.25 day-count)."""
        r = compute_xirr([(D0, -10000.0), (_days(365), 11000.0)])
        assert r is not None
        assert r == pytest.approx(0.10, abs=2e-3)

    def test_late_repayment_degrades_xirr(self):
        """Same +11 000 but at J+730 → ~(1.1)^(1/2) − 1 ≈ 4.88 %.

        The exact root with the 365.25 day-count is (1.1)^(365.25/730) − 1.
        A one-year delay nearly halves the annualized return — that is the
        whole point of this metric vs the contractual rate.
        """
        r = compute_xirr([(D0, -10000.0), (_days(730), 11000.0)])
        assert r is not None
        exact = 1.1 ** (365.25 / 730) - 1  # ≈ 0.048843
        assert r == pytest.approx(exact, abs=1e-6)
        assert r == pytest.approx(0.0488, abs=1e-3)

    def test_in_progress_no_repayment_crd_terminal_is_zero_rate(self):
        """-10 000 a year ago, CRD 10 000 today as terminal value → ~0 %.

        The living capital is worth par: no gain, no loss, XIRR ≈ 0.
        """
        today = date.today()
        r = compute_xirr([(today - timedelta(days=365), -10000.0), (today, 10000.0)])
        assert r is not None
        assert r == pytest.approx(0.0, abs=1e-6)

    def test_default_with_partial_recovery_is_strongly_negative(self):
        """-10 000, only +2 000 recovered after a year → ≈ −80 %."""
        r = compute_xirr([(D0, -10000.0), (_days(365), 2000.0)])
        assert r is not None
        assert r == pytest.approx(-0.80, abs=3e-3)


class TestComputeXirrNoneConventions:
    """Cases where no meaningful rate exists → None (documented convention)."""

    def test_total_default_no_positive_flow_returns_none(self):
        """DEFAULTED project, zero repayment: only the outflow → None.

        Convention: with no inflow at all there is no root to solve for
        (NPV is negative for every rate) — we return None rather than an
        arbitrary floor like −100 %.
        """
        assert compute_xirr([(D0, -10000.0)]) is None
        assert compute_xirr([(D0, -10000.0), (_days(365), -5000.0)]) is None

    def test_only_positive_flows_returns_none(self):
        assert compute_xirr([(D0, 500.0), (_days(365), 500.0)]) is None

    def test_empty_and_single_flow_return_none(self):
        assert compute_xirr([]) is None
        assert compute_xirr([(D0, -10000.0)]) is None

    def test_span_under_30_days_returns_none(self):
        """Annualizing a 20-day flow is meaningless → None."""
        assert compute_xirr([(D0, -10000.0), (_days(20), 10100.0)]) is None

    def test_span_of_exactly_30_days_is_computed(self):
        """Boundary: 30 days is the first admissible span."""
        r = compute_xirr([(D0, -10000.0), (_days(30), 10100.0)])
        assert r is not None
        # (1.01)^(365.25/30) − 1 ≈ 12.87 % annualized
        assert r == pytest.approx(1.01 ** (365.25 / 30) - 1, abs=1e-4)

    def test_no_convergence_returns_none(self):
        """Root below the solver domain (−99 %): −10 000 → +1 in a year.

        The exact root is ≈ −99.99 %, outside Brent's [−0.99, 10] bracket, and
        Newton diverges (overflow past −100 %) → None.
        """
        assert compute_xirr([(D0, -10000.0), (_days(365), 1.0)]) is None
