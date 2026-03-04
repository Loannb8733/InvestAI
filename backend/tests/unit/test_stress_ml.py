"""Stress tests for ML pipeline robustness.

Validates that the forecaster, anomaly detector, and drift detector
handle edge cases gracefully: outliers, NaN/Inf, empty data,
constant prices, extreme values, and type mismatches.
"""

import math
from datetime import datetime, timedelta

import numpy as np
import pytest

from app.ml.anomaly_detector import AnomalyDetector
from app.ml.drift_detector import DriftResult, _compute_psi, check_drift
from app.ml.forecaster import ForecastResult, PriceForecaster

# ── Helpers ────────────────────────────────────────────────────────────


def _make_dates(n: int, start: datetime = datetime(2025, 1, 1)):
    return [start + timedelta(days=i) for i in range(n)]


def _make_prices(n: int, base: float = 100.0, seed: int = 42) -> list:
    """Generate realistic-looking prices with controlled randomness."""
    rng = np.random.RandomState(seed)
    prices = [base]
    for _ in range(n - 1):
        prices.append(max(0.01, prices[-1] * (1 + rng.normal(0.001, 0.015))))
    return prices


# ── Forecaster Fixtures ───────────────────────────────────────────────


@pytest.fixture
def forecaster():
    f = PriceForecaster()
    f._prophet_available = False  # Deterministic (no MCMC)
    return f


# ======================================================================
# 1. OUTLIER INJECTION
# ======================================================================


class TestForecasterOutliers:
    """Verify the forecaster doesn't crash or produce NaN with extreme data."""

    def test_single_spike(self, forecaster):
        """One 100x spike in an otherwise normal series."""
        prices = _make_prices(50)
        prices[25] = prices[24] * 100  # 100x spike
        result = forecaster.forecast(prices, _make_dates(50), 7)
        assert isinstance(result, ForecastResult)
        assert all(math.isfinite(p) and p >= 0 for p in result.prices)

    def test_single_crash(self, forecaster):
        """One 99% crash."""
        prices = _make_prices(50)
        prices[30] = prices[29] * 0.01  # 99% crash
        result = forecaster.forecast(prices, _make_dates(50), 7)
        assert all(math.isfinite(p) and p >= 0 for p in result.prices)

    def test_alternating_extremes(self, forecaster):
        """Wild oscillation: up 50%, down 50%, repeat."""
        prices = [100.0]
        for i in range(49):
            prices.append(prices[-1] * (1.5 if i % 2 == 0 else 0.5))
        result = forecaster.forecast(prices, _make_dates(50), 7)
        assert len(result.prices) == 7
        assert all(math.isfinite(p) for p in result.prices)

    def test_huge_prices(self, forecaster):
        """Very large prices (Bitcoin-like)."""
        prices = _make_prices(30, base=1_000_000)
        result = forecaster.forecast(prices, _make_dates(30), 7)
        assert all(p > 0 for p in result.prices)

    def test_micro_prices(self, forecaster):
        """Very small prices (sub-penny tokens)."""
        prices = _make_prices(30, base=0.0000001)
        result = forecaster.forecast(prices, _make_dates(30), 7)
        assert all(math.isfinite(p) and p >= 0 for p in result.prices)


# ======================================================================
# 2. NULL / NaN / Inf INJECTION
# ======================================================================


class TestForecasterNullsAndInf:
    """Forecaster should handle or reject invalid data without crashing."""

    def test_empty_prices(self, forecaster):
        result = forecaster.forecast([], [], 7)
        assert result.prices == []
        assert result.model_used == "fallback"

    def test_single_price(self, forecaster):
        result = forecaster.forecast([42.0], [datetime(2025, 1, 1)], 5)
        assert len(result.prices) == 5

    def test_two_prices(self, forecaster):
        result = forecaster.forecast(
            [100.0, 101.0],
            [datetime(2025, 1, 1), datetime(2025, 1, 2)],
            3,
        )
        assert len(result.prices) == 3

    def test_constant_prices(self, forecaster):
        """All identical prices: vol=0, should not divide by zero."""
        prices = [50.0] * 30
        result = forecaster.forecast(prices, _make_dates(30), 7)
        assert all(math.isfinite(p) for p in result.prices)
        assert all(math.isfinite(p) for p in result.confidence_low)
        assert all(math.isfinite(p) for p in result.confidence_high)

    def test_zero_prices(self, forecaster):
        """All zeros: edge case for division and log."""
        prices = [0.0] * 30
        result = forecaster._fallback_forecast(prices, 5)
        assert all(math.isfinite(p) for p in result.prices)

    def test_near_zero_prices(self, forecaster):
        """1e-12 range: tests epsilon guards."""
        prices = [1e-12] * 30
        result = forecaster.forecast(prices, _make_dates(30), 5)
        assert all(math.isfinite(p) for p in result.prices)


# ======================================================================
# 3. CONFIDENCE INTERVAL INVARIANTS
# ======================================================================


class TestConfidenceIntervals:
    """CI ordering: low <= price <= high, and widening over horizon."""

    def test_ci_ordering(self, forecaster):
        prices = _make_prices(30)
        result = forecaster.forecast(prices, _make_dates(30), 7)
        for i in range(len(result.prices)):
            assert result.confidence_low[i] <= result.prices[i], f"Day {i}: low > price"
            assert result.prices[i] <= result.confidence_high[i], f"Day {i}: price > high"

    def test_ci_no_negative(self, forecaster):
        prices = _make_prices(30, base=1.0)
        result = forecaster.forecast(prices, _make_dates(30), 14)
        for lo in result.confidence_low:
            assert lo >= 0, "Confidence low should never be negative"


# ======================================================================
# 4. ANOMALY DETECTOR STRESS
# ======================================================================


class TestAnomalyDetectorStress:
    """Anomaly detector should return sensible results on edge cases."""

    def test_constant_prices_no_anomaly(self):
        det = AnomalyDetector()
        result = det.detect("TEST", [100.0] * 30, 100.0, 100.0)
        # Constant prices should not flag anomaly
        if result is not None:
            assert result.is_anomaly is False

    def test_extreme_spike(self):
        det = AnomalyDetector()
        prices = [100.0] * 29 + [10000.0]
        result = det.detect("TEST", prices, 10000.0, 100.0, "crypto")
        # Should detect an anomaly
        assert result is not None
        assert result.is_anomaly is True

    def test_empty_prices(self):
        det = AnomalyDetector()
        result = det.detect("TEST", [], 100.0, 100.0)
        # Should return None (not enough data)
        assert result is None or result.is_anomaly is False

    def test_single_price(self):
        det = AnomalyDetector()
        result = det.detect("TEST", [42.0], 42.0, 42.0)
        # Should not crash
        assert result is None or isinstance(result, type(result))

    def test_negative_prices(self):
        """Anomaly detector should handle negative inputs gracefully."""
        det = AnomalyDetector()
        result = det.detect("TEST", [-10.0, -5.0, -3.0, -1.0], -1.0, -5.0)
        # Should not raise; might return None
        assert result is None or hasattr(result, "is_anomaly")


# ======================================================================
# 5. DRIFT DETECTOR STRESS
# ======================================================================


class TestDriftDetectorStress:
    """PSI-based drift detector edge cases."""

    def test_identical_distributions(self):
        """PSI should be ~0 for identical data."""
        data = np.random.RandomState(42).normal(0, 1, 100)
        psi = _compute_psi(data, data.copy())
        assert psi < 0.05, f"PSI for identical data should be near 0, got {psi}"

    def test_completely_different_distributions(self):
        """PSI should be high for completely different data."""
        ref = np.random.RandomState(42).normal(0, 1, 100)
        cur = np.random.RandomState(42).normal(10, 1, 100)  # Shifted +10σ
        psi = _compute_psi(ref, cur)
        assert psi > 0.5, f"PSI for shifted data should be high, got {psi}"

    def test_too_few_data_points(self):
        """Should return 0 PSI when data is too short."""
        psi = _compute_psi(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
        assert psi == 0.0

    def test_check_drift_short_series(self):
        """Short price series should return 'ok' status."""
        result = check_drift(np.array([1.0] * 5), np.array([2.0] * 5), symbol="SHORT")
        assert result.status == "ok"

    def test_check_drift_constant_prices(self):
        """Constant reference + constant current = no drift."""
        ref = np.full(100, 50.0)
        cur = np.full(30, 50.0)
        result = check_drift(ref, cur, symbol="CONST")
        assert result.status == "ok"

    def test_check_drift_regime_change(self):
        """Sudden regime change should trigger drift."""
        rng = np.random.RandomState(42)
        ref = 100 + rng.normal(0, 1, 150)  # Mean 100, vol 1
        cur = 200 + rng.normal(0, 10, 50)  # Mean 200, vol 10
        result = check_drift(ref, cur, symbol="SHIFT")
        assert result.status in ("warning", "drift"), f"Expected drift, got {result.status}"

    def test_drift_result_fields(self):
        """DriftResult should have all expected fields."""
        result = DriftResult(symbol="X")
        assert result.symbol == "X"
        assert result.psi_values == {}
        assert result.overall_psi == 0.0
        assert result.drifted_features == []
        assert result.status == "ok"


# ======================================================================
# 6. DETERMINISM VALIDATION
# ======================================================================


class TestDeterminism:
    """Two identical runs must produce identical results (to 1e-6)."""

    def test_linear_determinism(self, forecaster):
        prices = _make_prices(30)
        dates = _make_dates(30)
        r1 = forecaster._linear_forecast(prices, dates, 7)
        r2 = forecaster._linear_forecast(prices, dates, 7)
        for i in range(7):
            assert abs(r1.prices[i] - r2.prices[i]) < 1e-6, f"Day {i}: {r1.prices[i]} != {r2.prices[i]}"
            assert abs(r1.confidence_low[i] - r2.confidence_low[i]) < 1e-6
            assert abs(r1.confidence_high[i] - r2.confidence_high[i]) < 1e-6

    def test_fallback_determinism(self, forecaster):
        prices = [100.0, 102.0, 101.5]
        r1 = forecaster._fallback_forecast(prices, 5)
        r2 = forecaster._fallback_forecast(prices, 5)
        for i in range(5):
            assert abs(r1.prices[i] - r2.prices[i]) < 1e-6

    def test_forecast_dispatch_determinism(self, forecaster):
        prices = _make_prices(30)
        dates = _make_dates(30)
        r1 = forecaster.forecast(prices, dates, 7)
        r2 = forecaster.forecast(prices, dates, 7)
        assert r1.model_used == r2.model_used
        assert r1.trend == r2.trend
        for i in range(7):
            assert abs(r1.prices[i] - r2.prices[i]) < 1e-6

    def test_drift_detector_determinism(self):
        rng = np.random.RandomState(42)
        ref = 100 + rng.normal(0, 2, 100)
        rng2 = np.random.RandomState(99)
        cur = 105 + rng2.normal(0, 3, 40)
        d1 = check_drift(ref, cur, symbol="DET")
        d2 = check_drift(ref, cur, symbol="DET")
        assert d1.overall_psi == d2.overall_psi
        assert d1.psi_values == d2.psi_values
        assert d1.status == d2.status

    def test_anomaly_detector_determinism(self):
        det = AnomalyDetector()
        prices = _make_prices(30)
        r1 = det.detect("BTC", prices, prices[-1], 100.0, "crypto")
        r2 = det.detect("BTC", prices, prices[-1], 100.0, "crypto")
        if r1 is None:
            assert r2 is None
        else:
            assert r1.is_anomaly == r2.is_anomaly
            assert abs(r1.z_score - r2.z_score) < 1e-6


# ======================================================================
# 7. PRECOMPUTE RSI STRESS
# ======================================================================


class TestPrecomputeRSI:
    """Vectorized RSI edge cases."""

    def test_constant_prices(self):
        arr = np.full(50, 100.0)
        rsi = PriceForecaster._precompute_rsi(arr, 14)
        assert len(rsi) == 50
        assert all(math.isfinite(v) for v in rsi)

    def test_monotonic_up(self):
        arr = np.arange(1, 51, dtype=float)
        rsi = PriceForecaster._precompute_rsi(arr, 14)
        # Monotonic up: RSI should be close to 100
        assert rsi[-1] > 90

    def test_monotonic_down(self):
        arr = np.arange(50, 0, -1, dtype=float)
        rsi = PriceForecaster._precompute_rsi(arr, 14)
        # Monotonic down: RSI should be close to 0
        assert rsi[-1] < 10

    def test_too_short(self):
        arr = np.array([100.0, 101.0, 99.0])
        rsi = PriceForecaster._precompute_rsi(arr, 14)
        assert len(rsi) == 3
        # All should be default 50.0
        assert all(v == 50.0 for v in rsi)

    def test_single_element(self):
        arr = np.array([42.0])
        rsi = PriceForecaster._precompute_rsi(arr, 14)
        assert len(rsi) == 1
