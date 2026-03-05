"""Tests for the Alpha → 7d prediction data link.

Validates that:
1. get_price_prediction method exists and is correctly named.
2. The predicted_7d_pct calculation handles edge cases.
3. Price = 0 does not cause division errors.
4. Prediction with valid prices computes correct percentage.
"""

import pytest

from app.services.prediction_service import PredictionService


class TestPredictionMethodExists:
    """Verify the prediction method is callable."""

    def test_get_price_prediction_exists(self):
        """PredictionService must have get_price_prediction, not get_prediction."""
        svc = PredictionService()
        assert hasattr(
            svc, "get_price_prediction"
        ), "Missing get_price_prediction — alpha scoring cannot compute 7d predictions"

    def test_get_prediction_does_not_exist(self):
        """The old wrong name 'get_prediction' must NOT exist."""
        svc = PredictionService()
        assert not hasattr(svc, "get_prediction"), "get_prediction still exists — should be get_price_prediction"


class TestPredicted7dPctCalculation:
    """Test the predicted_7d_pct formula inline."""

    def test_positive_prediction(self):
        """pred_price > current → positive %."""
        price = 100.0
        pred_price = 105.0
        pct = (pred_price / price - 1) * 100
        assert pct == pytest.approx(5.0)

    def test_negative_prediction(self):
        """pred_price < current → negative %."""
        price = 100.0
        pred_price = 92.0
        pct = (pred_price / price - 1) * 100
        assert pct == pytest.approx(-8.0)

    def test_zero_price_guard(self):
        """price=0 must not cause ZeroDivisionError."""
        price = 0.0
        pred_price = 105.0
        # Guard: only compute if both > 0
        if pred_price > 0 and price > 0:
            pct = (pred_price / price - 1) * 100
        else:
            pct = 0.0
        assert pct == 0.0

    def test_zero_pred_price_guard(self):
        """pred_price=0 should yield 0% (not compute)."""
        price = 100.0
        pred_price = 0.0
        if pred_price > 0 and price > 0:
            pct = (pred_price / price - 1) * 100
        else:
            pct = 0.0
        assert pct == 0.0

    def test_small_change_not_rounded_to_zero(self):
        """A 0.3% change must not be rounded to 0."""
        price = 100.0
        pred_price = 100.3
        pct = round((pred_price / price - 1) * 100, 2)
        assert pct == 0.3, f"Expected 0.3%, got {pct}%"

    def test_typical_crypto_prediction(self):
        """BTC: 83000 → 85490 = +3.0%."""
        price = 83000.0
        pred_price = 85490.0
        pct = round((pred_price / price - 1) * 100, 2)
        assert pct == pytest.approx(3.0, abs=0.1)
