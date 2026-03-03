"""Anomaly detection using Isolation Forest and Z-score."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np

from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext

logger = logging.getLogger(__name__)


def _returns_hash(prices: List[float]) -> str:
    """Hash price data to detect staleness for model caching.

    Samples 10 evenly-spaced points plus extremes so that two series with
    identical length/first/last but different intermediate data produce
    different hashes.
    """
    if not prices:
        return "empty"
    n = len(prices)
    indices = sorted(set([0, n - 1] + [i * n // 10 for i in range(10)]))
    sample = [round(prices[i], 8) for i in indices if i < n]
    raw = f"{n}:{sum(sample):.8f}:{':'.join(str(s) for s in sample)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# Configurable thresholds
ISOLATION_FOREST_CONTAMINATION = 0.05
ISOLATION_FOREST_N_ESTIMATORS = 100


@dataclass
class Anomaly:
    """Detected anomaly."""

    symbol: str
    is_anomaly: bool
    anomaly_type: Optional[str]  # price_spike, price_drop, volatility_spike
    severity: str  # low, medium, high
    description: str
    detected_at: datetime
    price_change_percent: float
    z_score: float


class AnomalyDetector:
    """Anomaly detection using Isolation Forest and statistical methods."""

    def __init__(self):
        self._sklearn_available = self._check_sklearn()

    @staticmethod
    def _check_sklearn() -> bool:
        """Check if scikit-learn is available."""
        try:
            from sklearn.ensemble import IsolationForest  # noqa: F401

            return True
        except ImportError:
            logger.warning("scikit-learn not available, using Z-score only")
            return False

    def detect(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        avg_buy_price: float,
        asset_type: str = "crypto",
        market_context: Optional[MarketContext] = None,
    ) -> Optional[Anomaly]:
        """Detect anomalies in price data.

        Uses Isolation Forest when enough data is available,
        falls back to Z-score and threshold-based detection.

        Args:
            symbol: Asset symbol.
            prices: Historical prices (recent last).
            current_price: Current market price.
            avg_buy_price: User's average buy price.
            asset_type: Type of asset for threshold calibration.
            market_context: Pre-computed MarketContext for adaptive thresholds.
        """
        if not prices or current_price == 0:
            return None

        # Method 1: Isolation Forest on returns (if enough data)
        if self._sklearn_available and len(prices) >= 30:
            anomaly = self._isolation_forest_detect(symbol, prices, current_price, asset_type)
            if anomaly:
                return anomaly

        # Method 2: Z-score on returns (adaptive threshold)
        if len(prices) >= 10:
            anomaly = self._zscore_detect(symbol, prices, current_price, asset_type, ctx=market_context)
            if anomaly:
                return anomaly

        # Method 3: Threshold-based (compare current vs avg buy price)
        return self._threshold_detect(symbol, current_price, avg_buy_price, asset_type, ctx=market_context)

    def _isolation_forest_detect(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        asset_type: str,
    ) -> Optional[Anomaly]:
        """Detect anomalies using Isolation Forest on log returns."""
        from sklearn.ensemble import IsolationForest

        arr = np.array(prices, dtype=float)
        # Compute log returns
        returns = np.diff(np.log(np.maximum(arr, 1e-10)))

        if len(returns) < 20:
            return None

        # P7: Try to load cached model from Redis (4h TTL)
        data_hash = _returns_hash(prices)
        model = self._get_cached_iforest(symbol, data_hash)

        if model is None:
            # Fit Isolation Forest
            model = IsolationForest(
                contamination=ISOLATION_FOREST_CONTAMINATION,
                random_state=42,
                n_estimators=ISOLATION_FOREST_N_ESTIMATORS,
            )
            X = returns.reshape(-1, 1)
            model.fit(X)
            # Cache the fitted model
            self._cache_iforest(symbol, data_hash, model)

        # Check most recent return
        latest_return = np.log(current_price / max(prices[-1], 1e-10))
        prediction = model.predict([[latest_return]])
        score = model.decision_function([[latest_return]])[0]

        if prediction[0] == -1:  # Anomaly detected
            pct_change = (current_price - prices[-1]) / prices[-1] * 100
            anomaly_type = "price_spike" if pct_change > 0 else "price_drop"

            # Severity from score (more negative = more anomalous)
            if score < -0.3:
                severity = "high"
            elif score < -0.15:
                severity = "medium"
            else:
                severity = "low"

            return Anomaly(
                symbol=symbol,
                is_anomaly=True,
                anomaly_type=anomaly_type,
                severity=severity,
                description=(
                    f"Mouvement anormal détecté par Isolation Forest: "
                    f"{'hausse' if pct_change > 0 else 'baisse'} de {abs(pct_change):.1f}% "
                    f"(score anomalie: {score:.2f})"
                ),
                detected_at=datetime.utcnow(),
                price_change_percent=round(pct_change, 2),
                z_score=round(float(-score * 10), 2),
            )

        return None

    def _zscore_detect(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        asset_type: str,
        ctx: Optional[MarketContext] = None,
    ) -> Optional[Anomaly]:
        """Detect anomalies using Z-score on returns with adaptive threshold."""
        arr = np.array(prices, dtype=float)
        returns = np.diff(arr) / arr[:-1]

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return None

        latest_return = (current_price - prices[-1]) / prices[-1]
        z = (latest_return - mean_return) / std_return

        # Adaptive threshold: higher for fat-tailed distributions (high kurtosis)
        threshold = at.anomaly_zscore_threshold(ctx) if ctx else (2.5 if asset_type == "crypto" else 3.0)

        if abs(z) > threshold:
            pct_change = latest_return * 100
            anomaly_type = "price_spike" if pct_change > 0 else "price_drop"

            if abs(z) > threshold * 1.5:
                severity = "high"
            elif abs(z) > threshold * 1.2:
                severity = "medium"
            else:
                severity = "low"

            return Anomaly(
                symbol=symbol,
                is_anomaly=True,
                anomaly_type=anomaly_type,
                severity=severity,
                description=(
                    f"Z-score anormal ({z:.1f}): "
                    f"{'hausse' if pct_change > 0 else 'baisse'} de {abs(pct_change):.1f}% "
                    f"vs moyenne {mean_return * 100:.2f}%"
                ),
                detected_at=datetime.utcnow(),
                price_change_percent=round(pct_change, 2),
                z_score=round(float(z), 2),
            )

        return None

    @staticmethod
    def _get_cached_iforest(symbol: str, data_hash: str):
        """Try to load cached Isolation Forest from Redis (sync, via event loop)."""
        try:
            from app.core.redis_client import get_cached_model

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — use a thread to avoid blocking
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, get_cached_model(symbol, "iforest", data_hash))
                    return future.result(timeout=5)
            else:
                return loop.run_until_complete(get_cached_model(symbol, "iforest", data_hash))
        except Exception as e:
            logger.debug("IForest cache miss for %s: %s", symbol, e)
            return None

    @staticmethod
    def _cache_iforest(symbol: str, data_hash: str, model):
        """Cache fitted Isolation Forest in Redis (4h TTL)."""
        try:
            from app.core.redis_client import cache_model

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule as a fire-and-forget task
                asyncio.ensure_future(cache_model(symbol, "iforest", data_hash, model, ttl=14400))
            else:
                loop.run_until_complete(cache_model(symbol, "iforest", data_hash, model, ttl=14400))
        except Exception as e:
            logger.debug("Failed to cache IForest for %s: %s", symbol, e)

    def _threshold_detect(
        self,
        symbol: str,
        current_price: float,
        avg_buy_price: float,
        asset_type: str,
        ctx: Optional[MarketContext] = None,
    ) -> Optional[Anomaly]:
        """Threshold-based anomaly detection using adaptive price threshold."""
        if avg_buy_price == 0:
            return None

        pct_change = (current_price - avg_buy_price) / avg_buy_price * 100
        # Adaptive threshold: uses 3σ of monthly returns instead of hardcoded 20%/10%
        threshold = at.anomaly_price_threshold(ctx) if ctx else (20.0 if asset_type == "crypto" else 10.0)

        if abs(pct_change) > threshold:
            anomaly_type = "price_spike" if pct_change > 0 else "price_drop"
            severity = "high" if abs(pct_change) > threshold * 2 else "medium"

            return Anomaly(
                symbol=symbol,
                is_anomaly=True,
                anomaly_type=anomaly_type,
                severity=severity,
                description=(
                    f"{'Hausse' if pct_change > 0 else 'Baisse'} significative "
                    f"de {abs(pct_change):.1f}% par rapport au prix d'achat moyen"
                ),
                detected_at=datetime.utcnow(),
                price_change_percent=round(pct_change, 2),
                z_score=0.0,
            )

        return None
