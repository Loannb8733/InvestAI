from datetime import timedelta
from typing import Any

from app.ml.forecaster import ForecastResult

CONFIDENCE = 0.05
WEIGHTS = {"Prophet": 60, "XGBoost": 40}


class DeterministicForecaster:
    """Double du PriceForecaster : prolonge la tendance des 7 derniers jours, sans entraîner de modèle."""

    def ensemble_forecast(self, prices: list[float], dates: list[Any], days_ahead: int = 7, **_: Any) -> ForecastResult:
        last = prices[-1]
        lookback = prices[-8] if len(prices) >= 8 else prices[0]
        daily = (last / lookback - 1) / 7 if lookback else 0.0
        path = [last * (1 + daily * (i + 1)) for i in range(days_ahead)]
        change = (path[-1] / last - 1) * 100 if last else 0.0
        trend = "bullish" if change > 1 else "bearish" if change < -1 else "neutral"
        return ForecastResult(
            dates=[(dates[-1] + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(days_ahead)],
            prices=path,
            confidence_low=[p * (1 - CONFIDENCE) for p in path],
            confidence_high=[p * (1 + CONFIDENCE) for p in path],
            trend=trend,
            trend_strength=min(100.0, abs(change) * 10),
            model_used="ensemble (prophet: 60%, xgboost: 40%)",
            models_detail=[
                {"name": name, "weight_pct": weight, "mape": 3.0 + i, "trend": trend}
                for i, (name, weight) in enumerate(WEIGHTS.items())
            ],
        )
