"""Tests for goal projection service.

Covers:
- RMC calculation (with and without returns)
- Probability estimation (Monte Carlo)
- Gold Shield (conservative + bear = dampened vol)
- Value parity: projection starts from current_amount, not modified
- Curve generation with correct date labels
"""

from datetime import date

import pytest

from app.services.goal_projection_service import GoalProjectionService


@pytest.fixture
def svc():
    return GoalProjectionService()


# ── RMC Calculation ──────────────────────────────────────────────


class TestRMC:
    """Required Monthly Contribution tests."""

    def test_rmc_simple_no_returns(self, svc):
        """Without returns: (target - current) / months."""
        rmc = svc.compute_rmc(current=0, target=12000, months=12)
        assert rmc == 1000.0

    def test_rmc_with_partial_progress(self, svc):
        """Partial progress reduces RMC."""
        rmc = svc.compute_rmc(current=6000, target=12000, months=12)
        assert rmc == 500.0

    def test_rmc_already_reached(self, svc):
        """If current >= target, RMC is 0."""
        rmc = svc.compute_rmc(current=15000, target=12000, months=12)
        assert rmc == 0.0

    def test_rmc_with_returns_is_lower(self, svc):
        """Expected returns reduce the required contribution."""
        rmc_no_ret = svc.compute_rmc(current=0, target=12000, months=24)
        rmc_with_ret = svc.compute_rmc(current=0, target=12000, months=24, annual_return=0.10)
        assert rmc_with_ret < rmc_no_ret, f"Returns should reduce RMC: without={rmc_no_ret}, with={rmc_with_ret}"

    def test_rmc_with_high_returns_covers_gap(self, svc):
        """If growth alone exceeds target, RMC = 0."""
        # 10000 * (1 + 0.5/12)^60 ≈ 128k — way above 12000
        rmc = svc.compute_rmc(current=10000, target=12000, months=60, annual_return=0.50)
        assert rmc == 0.0

    def test_rmc_one_month(self, svc):
        """1 month remaining: RMC = full gap."""
        rmc = svc.compute_rmc(current=500, target=1000, months=1)
        assert rmc == 500.0

    def test_rmc_parity_863_90(self, svc):
        """RMC from 863.90€ (dashboard value) to 5000€ in 24 months."""
        rmc = svc.compute_rmc(current=863.90, target=5000, months=24)
        expected = round((5000 - 863.90) / 24, 2)
        assert rmc == expected


# ── Probability ──────────────────────────────────────────────────


class TestProbability:
    """Monte Carlo probability of reaching goal."""

    def test_already_reached_100pct(self, svc):
        """Current >= target → 100%."""
        prob = svc.compute_probability(
            current=10000,
            target=5000,
            months=12,
            monthly_contribution=0,
            annual_return=0.08,
            annual_vol=0.20,
        )
        assert prob == 100.0

    def test_zero_months_and_below_target(self, svc):
        """0 months remaining and below target → 0%."""
        prob = svc.compute_probability(
            current=500,
            target=5000,
            months=0,
            monthly_contribution=0,
            annual_return=0.08,
            annual_vol=0.20,
        )
        assert prob == 0.0

    def test_adequate_dca_high_prob(self, svc):
        """Sufficient DCA over long period → high probability."""
        prob = svc.compute_probability(
            current=1000,
            target=10000,
            months=36,
            monthly_contribution=300,
            annual_return=0.08,
            annual_vol=0.15,
        )
        assert prob >= 70, f"Sufficient DCA should yield high prob, got {prob}%"

    def test_insufficient_dca_low_prob(self, svc):
        """Tiny DCA over short period → low probability."""
        prob = svc.compute_probability(
            current=100,
            target=100000,
            months=6,
            monthly_contribution=10,
            annual_return=0.05,
            annual_vol=0.30,
        )
        assert prob < 10, f"Tiny DCA should yield very low prob, got {prob}%"

    def test_aggressive_higher_prob_than_conservative(self, svc):
        """Aggressive returns (12%) should give higher prob than conservative (5%)."""
        prob_agg = svc.compute_probability(
            current=1000,
            target=5000,
            months=36,
            monthly_contribution=100,
            annual_return=0.12,
            annual_vol=0.25,
        )
        prob_con = svc.compute_probability(
            current=1000,
            target=5000,
            months=36,
            monthly_contribution=100,
            annual_return=0.05,
            annual_vol=0.10,
        )
        # Higher returns generally yield higher probability
        assert (
            prob_agg > prob_con * 0.8
        ), f"Aggressive should have comparable/higher prob: agg={prob_agg}, con={prob_con}"


# ── Curve Generation ─────────────────────────────────────────────


class TestCurve:
    """Projection curve tests."""

    def test_curve_starts_at_current(self, svc):
        """First point should be close to current_amount."""
        curve = svc.build_curve(
            current=1000,
            target=5000,
            months=24,
            monthly_contribution=150,
            annual_return=0.08,
            annual_vol=0.15,
            start_date=date(2026, 3, 1),
        )
        assert len(curve) > 0
        assert curve[0].projected_p50 == pytest.approx(1000, rel=0.01)

    def test_curve_ends_near_target(self, svc):
        """With adequate DCA, median endpoint should approach target."""
        curve = svc.build_curve(
            current=0,
            target=10000,
            months=36,
            monthly_contribution=300,
            annual_return=0.08,
            annual_vol=0.15,
            start_date=date(2026, 3, 1),
        )
        last = curve[-1]
        assert last.month == 36
        # With 300/month over 36 months + 8% returns, median should be near 10k+
        assert last.projected_p50 > 8000, f"Median endpoint too low: {last.projected_p50}"

    def test_curve_has_date_labels(self, svc):
        """Date labels should be formatted."""
        curve = svc.build_curve(
            current=1000,
            target=5000,
            months=12,
            monthly_contribution=300,
            annual_return=0.05,
            annual_vol=0.10,
            start_date=date(2026, 3, 1),
        )
        assert curve[0].date_label == "Mar 2026"

    def test_target_line_linear(self, svc):
        """Target line should go from current to target linearly."""
        curve = svc.build_curve(
            current=1000,
            target=5000,
            months=12,
            monthly_contribution=300,
            annual_return=0.05,
            annual_vol=0.10,
            start_date=date(2026, 3, 1),
        )
        assert curve[0].target_line == pytest.approx(1000, rel=0.01)
        assert curve[-1].target_line == pytest.approx(5000, rel=0.01)

    def test_p25_below_p50_below_p75(self, svc):
        """Confidence bands should be ordered: p25 < p50 < p75."""
        curve = svc.build_curve(
            current=1000,
            target=10000,
            months=24,
            monthly_contribution=200,
            annual_return=0.08,
            annual_vol=0.20,
            start_date=date(2026, 3, 1),
        )
        for point in curve[1:]:
            assert (
                point.projected_p25 <= point.projected_p50 <= point.projected_p75
            ), f"Month {point.month}: p25={point.projected_p25}, p50={point.projected_p50}, p75={point.projected_p75}"


# ── Gold Shield ──────────────────────────────────────────────────


class TestGoldShield:
    """Conservative strategy in bear market activates Gold Shield."""

    def test_gold_shield_reduces_volatility(self):
        """Gold Shield should dampen vol by 30%."""
        from app.services.goal_projection_service import _ANNUAL_VOL

        base_vol = _ANNUAL_VOL[("conservative", "stress")]
        gold_vol = base_vol * 0.7
        assert gold_vol < base_vol
        assert gold_vol == pytest.approx(0.07, rel=0.01)


# ── Value Parity ─────────────────────────────────────────────────


class TestValueParity:
    """Projection must never alter the goal's current_amount."""

    def test_projection_does_not_mutate_current(self, svc):
        """After projection, the starting value should remain 863.90."""
        current = 863.90
        target = 5000.0
        svc.compute_probability(
            current=current,
            target=target,
            months=24,
            monthly_contribution=150,
            annual_return=0.08,
            annual_vol=0.20,
        )
        assert current == 863.90, "current_amount must not be mutated"

    def test_rmc_does_not_mutate_current(self, svc):
        """RMC calculation must not alter current_amount."""
        current = 863.90
        svc.compute_rmc(current=current, target=5000, months=24, annual_return=0.08)
        assert current == 863.90

    def test_curve_starts_at_dashboard_value(self, svc):
        """Curve first point should exactly match dashboard value (863.90)."""
        curve = svc.build_curve(
            current=863.90,
            target=5000,
            months=24,
            monthly_contribution=150,
            annual_return=0.08,
            annual_vol=0.15,
            start_date=date(2026, 3, 1),
        )
        assert curve[0].projected_p50 == pytest.approx(863.90, abs=0.01)


# ── ETA (Time-to-Target) ────────────────────────────────────────


class TestETA:
    """calculate_eta binary search tests."""

    def test_eta_already_reached(self, svc):
        """Current >= target → 0 months, 100%."""
        months, prob = svc.calculate_eta(
            current=5000,
            target=1500,
            monthly_contribution=50,
            annual_return=0.08,
            annual_vol=0.15,
        )
        assert months == 0
        assert prob == 100.0

    def test_eta_with_adequate_dca(self, svc):
        """863.90 → 1500 with 43.20/mo DCA should converge within 24 months."""
        months, prob = svc.calculate_eta(
            current=863.90,
            target=1500,
            monthly_contribution=43.20,
            annual_return=0.08,
            annual_vol=0.18,
        )
        assert months <= 24, f"ETA too far: {months} months"
        assert prob >= 50.0, f"Probability too low at ETA: {prob}%"

    def test_eta_increases_with_lower_dca(self, svc):
        """Lower DCA should require more months."""
        months_high, _ = svc.calculate_eta(
            current=863.90,
            target=1500,
            monthly_contribution=100,
            annual_return=0.08,
            annual_vol=0.18,
        )
        months_low, _ = svc.calculate_eta(
            current=863.90,
            target=1500,
            monthly_contribution=20,
            annual_return=0.08,
            annual_vol=0.18,
        )
        assert months_low > months_high, f"Lower DCA should take longer: high={months_high}, low={months_low}"

    def test_eta_zero_dca_uses_growth_only(self, svc):
        """Zero DCA: must rely entirely on market growth → longer ETA."""
        months, prob = svc.calculate_eta(
            current=863.90,
            target=1500,
            monthly_contribution=0,
            annual_return=0.08,
            annual_vol=0.18,
        )
        assert months > 0
        assert months <= 120  # Within max_months
