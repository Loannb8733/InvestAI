import logging
from dataclasses import dataclass
from typing import Any

from app.domains.predictions.fallbacks import ema20_forecast, smart_round
from app.domains.predictions.types import ForecastPoint
from app.ml.forecasting.types import ForecastResult

logger = logging.getLogger(__name__)

MAX_MOVE_PCT = 50
ABERRANT = "prévision aberrante (au-delà de ±50 %)"


@dataclass
class Forecast:
    """Prévision prête à servir : points arrondis, tendance, modèles retenus et modèles écartés."""

    predictions: list[ForecastPoint]
    trend: str
    trend_strength: float
    model_used: str
    models_detail: list[dict[str, Any]]
    explanations: list[dict[str, Any]]
    skipped_models: list[dict[str, str]]


def _points(result: ForecastResult) -> list[ForecastPoint]:
    return [
        {
            "date": result.dates[i],
            "price": smart_round(result.prices[i]),
            "confidence_low": smart_round(result.confidence_low[i]),
            "confidence_high": smart_round(result.confidence_high[i]),
        }
        for i in range(len(result.dates))
    ]


def _clamped(predictions: list[ForecastPoint], current_price: float) -> list[ForecastPoint]:
    low = current_price * (1 - MAX_MOVE_PCT / 100)
    high = current_price * (1 + MAX_MOVE_PCT / 100)
    return [
        {
            **p,
            **{key: smart_round(min(max(p[key], low), high)) for key in ("price", "confidence_low", "confidence_high")},
        }
        for p in predictions
    ]


def sanity_checked(
    result: ForecastResult, prices: list[float], current_price: float, days_ahead: int, symbol: str
) -> Forecast:
    """Prévision de l'ensemble, remplacée par la pente de l'EMA-20 (ou bornée à ±50 % faute d'historique) si elle
    annonce plus de ±50 % ; l'ensemble écarté est alors ajouté aux modèles écartés."""
    predictions = _points(result)
    kept = Forecast(
        predictions,
        result.trend,
        result.trend_strength,
        result.model_used,
        result.models_detail,
        result.explanations,
        result.skipped_models,
    )
    if not predictions or current_price <= 0:
        return kept
    change_pct = (predictions[-1]["price"] - current_price) / current_price * 100
    if abs(change_pct) <= MAX_MOVE_PCT:
        return kept
    logger.warning(
        "SANITY CHECK: %s ensemble prediction unrealistic (%.1f%% in %dd). Falling back to EMA-20.",
        symbol,
        change_pct,
        days_ahead,
    )
    skipped = [*result.skipped_models, {"name": "ensemble", "reason": ABERRANT}]
    ema_predictions, ema_trend, ema_strength = ema20_forecast(prices, current_price, days_ahead)
    if ema_predictions:
        detail = [{"name": "EMA-20 (sanity fallback)", "weight_pct": 100, "mape": None, "trend": ema_trend}]
        return Forecast(ema_predictions, ema_trend, ema_strength, "ema20_sanity_fallback", detail, [], skipped)
    kept.predictions, kept.skipped_models = _clamped(predictions, current_price), skipped
    return kept
