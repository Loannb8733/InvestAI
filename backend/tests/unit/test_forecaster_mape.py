"""The reliability score must reflect the REAL walk-forward MAPE.

`models_detail["mape"]` (which drives the user-facing reliability/skill score) used
to come from `_quick_mape` — a directional proxy `abs(recent_change - predicted_change)`,
not an out-of-sample error. Meanwhile `_compute_weights` computes the true rolling
walk-forward MAPE per model and threw it away.

These tests pin the contract that the weight computation now surfaces the real
per-model MAPE so the score can be built on it.
"""

from datetime import datetime, timedelta

import pytest

from app.ml.forecaster import ForecastResult, PriceForecaster, _ensemble_total_variance_ci, _ou_reversion_speed


class TestEnsembleTotalVarianceCi:
    """Ensemble CI must combine the models' OWN (out-of-model) intervals via the
    law of total variance, not an in-sample empirical quantile."""

    def test_agreeing_models_use_within_variance_only(self):
        # Both models: point 100, native half-width 1.96 (=> std 1). Between-model
        # variance is 0, within is 1 => total std 1 => 95% CI = 100 +/- 1.96.
        lo, hi = _ensemble_total_variance_ci([100.0, 100.0], [1.96, 1.96], [0.5, 0.5], 100.0)
        assert lo == pytest.approx(98.04, abs=0.03)
        assert hi == pytest.approx(101.96, abs=0.03)

    def test_disagreeing_models_widen_via_between_variance(self):
        # Points 100 and 110 around mid 105 inject between-model dispersion, so the
        # ensemble interval is wider than any single model's native half-width.
        lo, hi = _ensemble_total_variance_ci([100.0, 110.0], [1.96, 1.96], [0.5, 0.5], 105.0)
        assert (hi - lo) / 2 > 1.96
        assert lo < 105 < hi

    def test_zero_native_width_uses_point_dispersion_only(self):
        # No native intervals => CI driven purely by the spread of point forecasts.
        lo, hi = _ensemble_total_variance_ci([100.0, 110.0], [0.0, 0.0], [0.5, 0.5], 105.0)
        assert hi > lo
        assert lo < 105 < hi


class TestOuReversionSpeed:
    """Mean-reversion (OU) must not fake reversion on a trending / unit-root series.

    A phi at/above ~1 means the series has a (near-)unit root — it is trending, not
    mean-reverting. Forcing phi to 0.999 imposed reversion that isn't there and
    biased the ensemble against the trend.
    """

    def test_unit_root_gives_no_reversion(self):
        # phi >= 0.98 -> theta 0 -> the OU forecast stays flat (random walk).
        assert _ou_reversion_speed(1.05) == 0.0
        assert _ou_reversion_speed(1.0) == 0.0
        assert _ou_reversion_speed(0.99) == 0.0
        assert _ou_reversion_speed(0.98) == 0.0

    def test_genuinely_reverting_series_keeps_speed(self):
        # A clearly stationary phi still reverts.
        assert _ou_reversion_speed(0.90) == pytest.approx(0.1053605, rel=1e-4)  # -ln(0.9)

    def test_tiny_phi_is_floored(self):
        # phi below the floor is clamped to 0.01 (finite, positive theta), not 0/neg.
        assert _ou_reversion_speed(-0.5) == pytest.approx(4.60517, rel=1e-4)  # -ln(0.01)
        assert _ou_reversion_speed(0.0) == pytest.approx(4.60517, rel=1e-4)


def _fr(prices):
    """Minimal ForecastResult carrying a prediction path."""
    return ForecastResult(
        dates=[],
        prices=list(prices),
        confidence_low=list(prices),
        confidence_high=list(prices),
        trend="neutral",
        trend_strength=0.0,
        model_used="mock",
    )


def _series(n):
    prices = [100.0 + i for i in range(n)]
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    return prices, dates


def test_compute_weights_single_returns_real_mapes():
    f = PriceForecaster()
    prices, dates = _series(20)
    split = 5
    actual = prices[-split:]

    def fake_run(name, train_prices, train_dates, horizon):
        if name == "perfect":
            return _fr(actual)  # 0% error
        return _fr([a * 1.10 for a in actual])  # 10% error

    from unittest.mock import patch

    with patch.object(f, "_run_model_by_name", side_effect=fake_run):
        weights, mapes = f._compute_weights_single(prices, dates, [("perfect", None), ("off10", None)], split=split)

    assert len(mapes) == 2
    assert mapes[0] == pytest.approx(0.1, abs=0.05)  # ~0, floored to 0.1
    assert mapes[1] == pytest.approx(10.0, rel=0.02)  # real out-of-sample MAPE
    assert weights[0] > weights[1]  # the accurate model is weighted higher


def test_compute_weights_surfaces_per_model_mape():
    """The caller-facing return now carries the real MAPE, not just weights."""
    f = PriceForecaster()
    prices, dates = _series(20)  # < 28 -> single-window path
    split = min(7, len(prices) // 2)
    actual = prices[-split:]

    def fake_run(name, train_prices, train_dates, horizon):
        if name == "perfect":
            return _fr(actual)
        return _fr([a * 1.10 for a in actual])

    from unittest.mock import patch

    with patch.object(f, "_run_model_by_name", side_effect=fake_run):
        weights, ci_cal, mapes = f._compute_weights(prices, dates, [("perfect", None), ("off10", None)])

    assert len(weights) == 2
    assert len(mapes) == 2
    assert ci_cal == 1.0
    assert mapes[1] == pytest.approx(10.0, rel=0.05)
