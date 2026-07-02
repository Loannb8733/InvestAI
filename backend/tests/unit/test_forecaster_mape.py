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

from app.ml.forecaster import ForecastResult, PriceForecaster


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
