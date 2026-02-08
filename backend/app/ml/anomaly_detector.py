"""Anomaly detection using Isolation Forest and Z-score."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


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
        """
        if not prices or current_price == 0:
            return None

        # Method 1: Isolation Forest on returns (if enough data)
        if self._sklearn_available and len(prices) >= 30:
            anomaly = self._isolation_forest_detect(symbol, prices, current_price, asset_type)
            if anomaly:
                return anomaly

        # Method 2: Z-score on returns
        if len(prices) >= 10:
            anomaly = self._zscore_detect(symbol, prices, current_price, asset_type)
            if anomaly:
                return anomaly

        # Method 3: Threshold-based (compare current vs avg buy price)
        return self._threshold_detect(symbol, current_price, avg_buy_price, asset_type)

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

        # Fit Isolation Forest
        model = IsolationForest(
            contamination=0.05,  # Expect 5% anomalies
            random_state=42,
            n_estimators=100,
        )
        X = returns.reshape(-1, 1)
        model.fit(X)

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
    ) -> Optional[Anomaly]:
        """Detect anomalies using Z-score on returns."""
        arr = np.array(prices, dtype=float)
        returns = np.diff(arr) / arr[:-1]

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return None

        latest_return = (current_price - prices[-1]) / prices[-1]
        z = (latest_return - mean_return) / std_return

        # Threshold depends on asset type
        threshold = 2.5 if asset_type == "crypto" else 3.0

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

    def _threshold_detect(
        self,
        symbol: str,
        current_price: float,
        avg_buy_price: float,
        asset_type: str,
    ) -> Optional[Anomaly]:
        """Simple threshold-based anomaly detection."""
        if avg_buy_price == 0:
            return None

        pct_change = (current_price - avg_buy_price) / avg_buy_price * 100
        threshold = 20 if asset_type == "crypto" else 10

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
