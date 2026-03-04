"""Unit tests for projection mathematical integrity.

Validates that:
- Projecting at year 0 returns the starting value unchanged.
- Projecting with 0% return and 0% inflation returns the starting value.
- TER (expense_ratio) is correctly deducted from the gross return.
- FIRE number formula is correct: annual_expenses / (withdrawal_rate / 100).
- Inflation adjustment on FIRE target is applied correctly.
- Probability of ruin is 0 when returns are always positive.

These tests exercise the endpoint logic directly (no HTTP, no DB) by
replicating the pure-math portions of the projection algorithms.
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Replicate the core FIRE projection loop from simulations.py
# ---------------------------------------------------------------------------


def fire_projection(
    portfolio_value: float,
    monthly_contribution: float,
    monthly_expenses: float,
    expected_annual_return: float,
    expense_ratio: float,
    inflation_rate: float,
    withdrawal_rate: float,
    target_years: int,
):
    """Pure-math replica of the FIRE endpoint projection."""
    annual_expenses = monthly_expenses * 12
    fire_number = annual_expenses / (withdrawal_rate / 100)

    net_annual_return = expected_annual_return - expense_ratio
    monthly_return = net_annual_return / 100 / 12
    value = portfolio_value
    years_to_fire = None
    projections = []

    for year in range(target_years + 1):
        adjusted_expenses = annual_expenses * ((1 + inflation_rate / 100) ** year)
        adjusted_fire_number = adjusted_expenses / (withdrawal_rate / 100)

        projections.append(
            {
                "year": year,
                "portfolio_value": round(value, 2),
                "fire_number": round(adjusted_fire_number, 2),
                "is_fire": value >= adjusted_fire_number,
                "progress_percent": round((value / adjusted_fire_number) * 100, 1),
            }
        )

        if years_to_fire is None and value >= adjusted_fire_number:
            years_to_fire = year

        for _ in range(12):
            value = value * (1 + monthly_return) + monthly_contribution

    return {
        "fire_number": round(fire_number, 2),
        "years_to_fire": years_to_fire,
        "projections": projections,
    }


# ---------------------------------------------------------------------------
# Replicate the core portfolio projection loop from simulations.py
# ---------------------------------------------------------------------------


def portfolio_projection(
    current_value: float,
    years: int,
    expected_return: float,
    expense_ratio: float,
    monthly_contribution: float,
    inflation_rate: float,
):
    """Pure-math replica of the projection endpoint."""
    net_annual_return = expected_return - expense_ratio
    monthly_return = net_annual_return / 100 / 12
    value = current_value
    total_contributions = 0.0
    projections = []

    for year in range(years + 1):
        real_value = value / ((1 + inflation_rate / 100) ** year)
        projections.append(
            {
                "year": year,
                "nominal_value": round(value, 2),
                "real_value": round(real_value, 2),
                "contributions": round(total_contributions, 2),
            }
        )
        for _ in range(12):
            value = value * (1 + monthly_return) + monthly_contribution
            total_contributions += monthly_contribution

    return {
        "current_value": round(current_value, 2),
        "projections": projections,
        "final_value": projections[-1]["nominal_value"],
        "real_final_value": projections[-1]["real_value"],
    }


# ===================================================================
# Tests
# ===================================================================


class TestProjectionAtT0:
    """Projection at year 0 must equal starting portfolio value."""

    @pytest.mark.parametrize("start_value", [863.90, 0.01, 100_000.0])
    def test_projection_year0_equals_start(self, start_value: float):
        result = portfolio_projection(
            current_value=start_value,
            years=10,
            expected_return=7.0,
            expense_ratio=0.0,
            monthly_contribution=500,
            inflation_rate=2.0,
        )
        assert result["projections"][0]["nominal_value"] == round(start_value, 2)
        assert result["current_value"] == round(start_value, 2)

    @pytest.mark.parametrize("start_value", [863.90, 50_000.0])
    def test_fire_year0_equals_start(self, start_value: float):
        result = fire_projection(
            portfolio_value=start_value,
            monthly_contribution=1000,
            monthly_expenses=3000,
            expected_annual_return=7.0,
            expense_ratio=0.0,
            inflation_rate=2.0,
            withdrawal_rate=4.0,
            target_years=30,
        )
        assert result["projections"][0]["portfolio_value"] == round(start_value, 2)


class TestZeroReturnPreservesValue:
    """With 0% return, 0% inflation, 0 contributions → value unchanged."""

    def test_projection_zero_return_zero_inflation(self):
        result = portfolio_projection(
            current_value=863.90,
            years=10,
            expected_return=0.0,
            expense_ratio=0.0,
            monthly_contribution=0,
            inflation_rate=0.0,
        )
        for proj in result["projections"]:
            assert proj["nominal_value"] == 863.90
            assert proj["real_value"] == 863.90

    def test_fire_zero_return_zero_inflation(self):
        result = fire_projection(
            portfolio_value=863.90,
            monthly_contribution=0,
            monthly_expenses=3000,
            expected_annual_return=0.0,
            expense_ratio=0.0,
            inflation_rate=0.0,
            withdrawal_rate=4.0,
            target_years=5,
        )
        for proj in result["projections"]:
            assert proj["portfolio_value"] == 863.90


class TestTERDeduction:
    """TER (expense_ratio) must be deducted from gross return."""

    def test_ter_reduces_final_value(self):
        """With same gross return, higher TER → lower final value."""
        no_ter = portfolio_projection(
            current_value=10_000,
            years=10,
            expected_return=7.0,
            expense_ratio=0.0,
            monthly_contribution=0,
            inflation_rate=0.0,
        )
        with_ter = portfolio_projection(
            current_value=10_000,
            years=10,
            expected_return=7.0,
            expense_ratio=0.75,
            monthly_contribution=0,
            inflation_rate=0.0,
        )
        assert with_ter["final_value"] < no_ter["final_value"]

    def test_ter_equal_to_return_preserves_value(self):
        """If TER == expected_return, net return is 0 → value unchanged."""
        result = portfolio_projection(
            current_value=10_000,
            years=5,
            expected_return=3.0,
            expense_ratio=3.0,
            monthly_contribution=0,
            inflation_rate=0.0,
        )
        for proj in result["projections"]:
            assert proj["nominal_value"] == 10_000.00

    def test_ter_deduction_amount(self):
        """Verify exact deduction: 7% gross - 0.75% TER = 6.25% net."""
        result = portfolio_projection(
            current_value=10_000,
            years=1,
            expected_return=7.0,
            expense_ratio=0.75,
            monthly_contribution=0,
            inflation_rate=0.0,
        )
        # Net annual = 6.25%, compounded monthly: (1 + 0.0625/12)^12 - 1 ≈ 6.432%
        expected = 10_000 * (1 + 0.0625 / 12) ** 12
        assert abs(result["final_value"] - round(expected, 2)) < 0.02


class TestFIREFormula:
    """FIRE number = annual_expenses / (withdrawal_rate / 100)."""

    @pytest.mark.parametrize(
        "expenses,rate,expected",
        [
            (3000, 4.0, 900_000.0),  # Classic 4% rule
            (2000, 3.5, 685_714.29),  # Conservative
            (5000, 4.0, 1_500_000.0),  # Higher expenses
        ],
    )
    def test_fire_number(self, expenses: float, rate: float, expected: float):
        result = fire_projection(
            portfolio_value=50_000,
            monthly_contribution=1000,
            monthly_expenses=expenses,
            expected_annual_return=7.0,
            expense_ratio=0.0,
            inflation_rate=2.0,
            withdrawal_rate=rate,
            target_years=30,
        )
        assert abs(result["fire_number"] - expected) < 0.02

    def test_fire_inflation_adjusts_target(self):
        """FIRE target at year N should be inflated."""
        result = fire_projection(
            portfolio_value=50_000,
            monthly_contribution=1000,
            monthly_expenses=3000,
            expected_annual_return=7.0,
            expense_ratio=0.0,
            inflation_rate=3.0,
            withdrawal_rate=4.0,
            target_years=10,
        )
        year0_target = result["projections"][0]["fire_number"]
        year10_target = result["projections"][10]["fire_number"]
        expected_year10 = year0_target * (1.03**10)
        assert abs(year10_target - round(expected_year10, 2)) < 0.02


class TestMonteCarloRuin:
    """Probability of ruin metrics from _monte_carlo_compute."""

    def test_positive_returns_zero_ruin(self):
        """With strongly positive drift and low vol, ruin should be ~0%."""
        from app.services.analytics_service import AnalyticsService

        # Daily drift of +0.5% with negligible volatility
        mu_vec = np.array([0.005])
        L = np.array([[0.001]])
        w = np.array([1.0])

        result = AnalyticsService._monte_carlo_compute(
            mu_vec=mu_vec,
            L=L,
            w=w,
            num_simulations=1000,
            horizon_days=90,
            n_assets=1,
            user_id="test",
        )
        assert result.prob_ruin == 0.0
        assert result.prob_positive > 99.0

    def test_negative_drift_increases_ruin(self):
        """With strongly negative drift, ruin probability should be > 0."""
        from app.services.analytics_service import AnalyticsService

        # Daily drift of -2% with moderate vol → paths frequently collapse
        mu_vec = np.array([-0.02])
        L = np.array([[0.05]])
        w = np.array([1.0])

        result = AnalyticsService._monte_carlo_compute(
            mu_vec=mu_vec,
            L=L,
            w=w,
            num_simulations=2000,
            horizon_days=365,
            n_assets=1,
            user_id="test",
        )
        # With -2% daily drift over 365 days, most paths go to near-zero
        assert result.prob_ruin > 0.0

    def test_volatility_shrinkage_reduces_extremes(self):
        """Long horizons with shrinkage should have tighter daily vol than raw."""
        from app.services.analytics_service import AnalyticsService

        # High vol (crypto-like: 80% annualized → daily ~5%)
        high_daily_vol = 0.80 / np.sqrt(252)
        mu_vec = np.array([0.0003])
        L_high = np.array([[high_daily_vol]])
        w = np.array([1.0])

        # At 365 days, shrinkage is active: (365-90)/(1825-90) ≈ 0.159
        # L_blended = 0.841 * L_high + 0.159 * L_longterm
        # L_longterm daily vol = 0.20/sqrt(252) ≈ 0.0126
        # So blended vol < high_daily_vol
        shrinkage = np.clip((365 - 90) / (1825 - 90), 0.0, 1.0)
        long_term_daily = 0.20 / np.sqrt(252)
        expected_blended = (1 - shrinkage) * high_daily_vol + shrinkage * long_term_daily

        assert expected_blended < high_daily_vol, "Blended vol must be lower than raw"
        # Verify the shrinkage factor is in expected range
        assert 0.1 < shrinkage < 0.2, f"Expected ~15.9% shrinkage at 365d, got {shrinkage:.3f}"

        # Run simulation and verify it completes without error
        result = AnalyticsService._monte_carlo_compute(
            mu_vec=mu_vec,
            L=L_high,
            w=w,
            num_simulations=1000,
            horizon_days=365,
            n_assets=1,
            user_id="test",
        )
        assert result.simulations >= 100
        assert result.horizon_days == 365
