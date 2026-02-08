"""Tests for ML price forecaster."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from app.ml.forecaster import ForecastResult, PriceForecaster


@pytest.fixture
def forecaster():
    """Create a PriceForecaster instance (Prophet disabled for unit tests)."""
    f = PriceForecaster()
    f._prophet_available = False  # Force linear/fallback for deterministic tests
    return f


@pytest.fixture
def sample_prices():
    """Generate sample price data with upward trend."""
    np.random.seed(42)
    base = 100.0
    prices = []
    for i in range(30):
        base *= 1 + np.random.normal(0.002, 0.01)
        prices.append(round(base, 2))
    return prices


@pytest.fixture
def sample_dates():
    """Generate 30 days of dates."""
    start = datetime(2025, 1, 1)
    return [start + timedelta(days=i) for i in range(30)]


class TestComputeTrend:
    """Tests for _compute_trend static method."""

    def test_bullish_trend(self):
        historical = [100, 101, 102, 103, 105]
        trend, strength = PriceForecaster._compute_trend(105, 115, historical)
        assert trend == "bullish"
        assert strength > 0

    def test_bearish_trend(self):
        historical = [105, 103, 102, 101, 100]
        trend, strength = PriceForecaster._compute_trend(100, 90, historical)
        assert trend == "bearish"
        assert strength > 0

    def test_neutral_trend(self):
        historical = [100, 100.5, 100.2, 100.3, 100.1]
        trend, strength = PriceForecaster._compute_trend(100.1, 100.2, historical)
        assert trend == "neutral"

    def test_zero_current_price(self):
        trend, strength = PriceForecaster._compute_trend(0, 100, [50, 60, 70])
        assert trend == "neutral"
        assert strength == 0.0

    def test_strength_capped_at_100(self):
        historical = [50, 60, 70, 80, 100]
        trend, strength = PriceForecaster._compute_trend(100, 200, historical)
        assert strength <= 100.0

    def test_short_historical(self):
        """With <5 data points, only prediction change is used."""
        trend, strength = PriceForecaster._compute_trend(100, 110, [98, 100])
        assert trend == "bullish"

    def test_momentum_weight(self):
        """Momentum (40%) should influence trend direction."""
        # Prediction says up 1% (below threshold alone), but strong momentum
        historical = [90, 92, 95, 98, 100]  # +11% momentum
        trend, _ = PriceForecaster._compute_trend(100, 101, historical)
        assert trend == "bullish"  # momentum pulls it bullish


class TestLinearForecast:
    """Tests for _linear_forecast method."""

    def test_returns_forecast_result(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        assert isinstance(result, ForecastResult)
        assert result.model_used == "linear"

    def test_correct_number_of_predictions(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        assert len(result.dates) == 7
        assert len(result.prices) == 7
        assert len(result.confidence_low) == 7
        assert len(result.confidence_high) == 7

    def test_confidence_intervals_ordered(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        for i in range(7):
            assert result.confidence_low[i] <= result.prices[i]
            assert result.prices[i] <= result.confidence_high[i]

    def test_confidence_widens_over_time(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        width_first = result.confidence_high[0] - result.confidence_low[0]
        width_last = result.confidence_high[-1] - result.confidence_low[-1]
        assert width_last > width_first

    def test_no_negative_prices(self, forecaster, sample_dates):
        # Very low prices
        prices = [0.001] * 30
        result = forecaster._linear_forecast(prices, sample_dates, 7)
        for p in result.prices:
            assert p >= 0.0

    def test_dates_are_future(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        last_historical = sample_dates[-1]
        for date_str in result.dates:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            assert date > last_historical

    def test_trend_is_valid(self, forecaster, sample_prices, sample_dates):
        result = forecaster._linear_forecast(sample_prices, sample_dates, 7)
        assert result.trend in ("bullish", "bearish", "neutral")
        assert 0 <= result.trend_strength <= 100


class TestFallbackForecast:
    """Tests for _fallback_forecast method."""

    def test_empty_prices(self, forecaster):
        result = forecaster._fallback_forecast([], 7)
        assert result.dates == []
        assert result.prices == []
        assert result.trend == "neutral"
        assert result.model_used == "fallback"

    def test_single_price(self, forecaster):
        result = forecaster._fallback_forecast([100.0], 5)
        assert len(result.prices) == 5
        assert result.model_used == "fallback"

    def test_no_negative_prices(self, forecaster):
        result = forecaster._fallback_forecast([1.0], 7)
        for p in result.prices:
            assert p >= 0.0
        for p in result.confidence_low:
            assert p >= 0.0


class TestForecastDispatch:
    """Tests for forecast() dispatcher method."""

    def test_few_prices_uses_fallback(self, forecaster):
        result = forecaster.forecast([100, 101, 102], [datetime.now()] * 3, 5)
        assert result.model_used == "fallback"

    def test_enough_prices_uses_linear(self, forecaster, sample_prices, sample_dates):
        result = forecaster.forecast(sample_prices, sample_dates, 7)
        assert result.model_used == "linear"

    def test_custom_days_ahead(self, forecaster, sample_prices, sample_dates):
        result = forecaster.forecast(sample_prices, sample_dates, 14)
        assert len(result.prices) == 14
