"""Détection d'anomalies de prix : Isolation Forest, z-score des rendements, puis écart au prix de revient."""

import asyncio
import concurrent.futures
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext

logger = logging.getLogger(__name__)

ISOLATION_FOREST_CONTAMINATION = 0.05
ISOLATION_FOREST_N_ESTIMATORS = 100
MODEL_TTL_S = 14400
_pending: set[asyncio.Future[Any]] = set()


def _returns_hash(prices: list[float]) -> str:
    """Empreinte d'une série (longueur, extrémités et dix points répartis) qui date le modèle en cache."""
    if not prices:
        return "empty"
    n = len(prices)
    indices = sorted({0, n - 1, *(i * n // 10 for i in range(10))})
    sample = [round(prices[i], 8) for i in indices if i < n]
    raw = f"{n}:{sum(sample):.8f}:{':'.join(str(s) for s in sample)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Anomaly:
    """Anomalie détectée : hausse ou baisse brutale (``price_spike``, ``price_drop``) et sa gravité."""

    symbol: str
    is_anomaly: bool
    anomaly_type: str | None
    severity: str
    description: str
    detected_at: datetime
    price_change_percent: float
    z_score: float


def _direction(pct_change: float) -> str:
    return "price_spike" if pct_change > 0 else "price_drop"


def _get_cached_iforest(symbol: str, data_hash: str) -> Any:
    try:
        from app.core.redis_client import get_cached_model

        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, get_cached_model(symbol, "iforest", data_hash))
                return future.result(timeout=5)
        return loop.run_until_complete(get_cached_model(symbol, "iforest", data_hash))
    except Exception as e:  # noqa: BLE001
        logger.debug("IForest cache miss for %s: %s", symbol, e)
        return None


def _cache_iforest(symbol: str, data_hash: str, model: Any) -> None:
    try:
        from app.core.redis_client import cache_model

        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = asyncio.ensure_future(cache_model(symbol, "iforest", data_hash, model, ttl=MODEL_TTL_S))
            _pending.add(task)
            task.add_done_callback(_pending.discard)
        else:
            loop.run_until_complete(cache_model(symbol, "iforest", data_hash, model, ttl=MODEL_TTL_S))
    except Exception as e:  # noqa: BLE001
        logger.debug("Failed to cache IForest for %s: %s", symbol, e)


def _iforest_severity(score: float) -> str:
    if score < -0.3:
        return "high"
    if score < -0.15:
        return "medium"
    return "low"


class AnomalyDetector:
    """Anomalies de prix d'un actif, par la première méthode qui en trouve une."""

    def __init__(self) -> None:
        self._sklearn_available = self._check_sklearn()

    @staticmethod
    def _check_sklearn() -> bool:
        try:
            from sklearn.ensemble import IsolationForest  # noqa: F401

            return True
        except ImportError:
            logger.warning("scikit-learn not available, using Z-score only")
            return False

    def detect(
        self,
        symbol: str,
        prices: list[float],
        current_price: float,
        avg_buy_price: float,
        asset_type: str = "crypto",
        market_context: MarketContext | None = None,
    ) -> Anomaly | None:
        """Isolation Forest dès 30 cours, z-score dès 10, sinon écart au prix d'achat moyen ; None sans anomalie."""
        if not prices or current_price == 0:
            return None
        if self._sklearn_available and len(prices) >= 30:
            anomaly = self._isolation_forest_detect(symbol, prices, current_price)
            if anomaly:
                return anomaly
        if len(prices) >= 10:
            anomaly = self._zscore_detect(symbol, prices, current_price, asset_type, ctx=market_context)
            if anomaly:
                return anomaly
        return self._threshold_detect(symbol, current_price, avg_buy_price, asset_type, ctx=market_context)

    def _isolation_forest_detect(self, symbol: str, prices: list[float], current_price: float) -> Anomaly | None:
        from sklearn.ensemble import IsolationForest

        arr = np.array(prices, dtype=float)
        returns = np.diff(np.log(np.maximum(arr, 1e-10)))
        if len(returns) < 20:
            return None
        data_hash = _returns_hash(prices)
        model = _get_cached_iforest(symbol, data_hash)
        if model is None:
            model = IsolationForest(
                contamination=ISOLATION_FOREST_CONTAMINATION,
                random_state=42,
                n_estimators=ISOLATION_FOREST_N_ESTIMATORS,
            )
            model.fit(returns.reshape(-1, 1))
            _cache_iforest(symbol, data_hash, model)
        latest_return = np.log(current_price / max(prices[-1], 1e-10))
        if model.predict([[latest_return]])[0] != -1:
            return None
        score = model.decision_function([[latest_return]])[0]
        pct_change = (current_price - prices[-1]) / prices[-1] * 100
        return Anomaly(
            symbol=symbol,
            is_anomaly=True,
            anomaly_type=_direction(pct_change),
            severity=_iforest_severity(score),
            description=(
                f"Mouvement anormal détecté par Isolation Forest: "
                f"{'hausse' if pct_change > 0 else 'baisse'} de {abs(pct_change):.1f}% "
                f"(score anomalie: {score:.2f})"
            ),
            detected_at=datetime.now(UTC),
            price_change_percent=round(pct_change, 2),
            z_score=round(float(-score * 10), 2),
        )

    def _zscore_detect(
        self,
        symbol: str,
        prices: list[float],
        current_price: float,
        asset_type: str,
        ctx: MarketContext | None = None,
    ) -> Anomaly | None:
        """Dernier rendement à plus de 2,5 (crypto) ou 3 écarts-types de la moyenne, ou au seuil adaptatif."""
        arr = np.array(prices, dtype=float)
        returns = np.diff(arr) / arr[:-1]
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return == 0:
            return None
        latest_return = (current_price - prices[-1]) / prices[-1]
        z = (latest_return - mean_return) / std_return
        threshold = at.anomaly_zscore_threshold(ctx) if ctx else (2.5 if asset_type == "crypto" else 3.0)
        if abs(z) <= threshold:
            return None
        pct_change = latest_return * 100
        if abs(z) > threshold * 1.5:
            severity = "high"
        elif abs(z) > threshold * 1.2:
            severity = "medium"
        else:
            severity = "low"
        return Anomaly(
            symbol=symbol,
            is_anomaly=True,
            anomaly_type=_direction(pct_change),
            severity=severity,
            description=(
                f"Z-score anormal ({z:.1f}): "
                f"{'hausse' if pct_change > 0 else 'baisse'} de {abs(pct_change):.1f}% "
                f"vs moyenne {mean_return * 100:.2f}%"
            ),
            detected_at=datetime.now(UTC),
            price_change_percent=round(pct_change, 2),
            z_score=round(float(z), 2),
        )

    def _threshold_detect(
        self,
        symbol: str,
        current_price: float,
        avg_buy_price: float,
        asset_type: str,
        ctx: MarketContext | None = None,
    ) -> Anomaly | None:
        """Écart au prix d'achat moyen au-delà de 20 % (crypto) ou 10 %, ou de trois écarts-types mensuels."""
        if avg_buy_price == 0:
            return None
        pct_change = (current_price - avg_buy_price) / avg_buy_price * 100
        threshold = at.anomaly_price_threshold(ctx) if ctx else (20.0 if asset_type == "crypto" else 10.0)
        if abs(pct_change) <= threshold:
            return None
        return Anomaly(
            symbol=symbol,
            is_anomaly=True,
            anomaly_type=_direction(pct_change),
            severity="high" if abs(pct_change) > threshold * 2 else "medium",
            description=(
                f"{'Hausse' if pct_change > 0 else 'Baisse'} significative "
                f"de {abs(pct_change):.1f}% par rapport au prix d'achat moyen"
            ),
            detected_at=datetime.now(UTC),
            price_change_percent=round(pct_change, 2),
            z_score=0.0,
        )
