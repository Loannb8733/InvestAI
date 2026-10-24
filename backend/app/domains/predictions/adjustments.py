from typing import Any

import numpy as np

from app.domains.predictions.fallbacks import smart_round
from app.domains.predictions.types import ForecastPoint
from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext

ILLIQUID_VOLUME = 1_000_000


def widen_intervals(predictions: list[ForecastPoint], factor: float) -> None:
    for pred in predictions:
        width = pred["confidence_high"] - pred["confidence_low"]
        pred["confidence_low"] = smart_round(pred["confidence_low"] - width * factor)
        pred["confidence_high"] = smart_round(pred["confidence_high"] + width * factor)


def _dampen(predictions: list[ForecastPoint], current_price: float, adj_factor: float) -> None:
    for pred in predictions:
        original_price = pred["price"]
        dampened = current_price + (original_price - current_price) * (1.0 - adj_factor)
        pred["price"] = smart_round(dampened)
        if original_price != 0:
            ratio = dampened / original_price
            pred["confidence_low"] = smart_round(pred["confidence_low"] * ratio)
            pred["confidence_high"] = smart_round(pred["confidence_high"] * ratio)


def _reclassified_trend(
    predictions: list[ForecastPoint], current_price: float, ctx: MarketContext, days_ahead: int
) -> str:
    new_final = predictions[-1]["price"]
    pct = (new_final - current_price) / current_price * 100 if current_price > 0 else 0
    threshold = at.trend_significance_threshold(ctx, days_ahead)
    if pct > threshold:
        return "bullish"
    if pct < -threshold:
        return "bearish"
    return "neutral"


def _mark_adjusted(regime_info: dict[str, Any], adj_factor: float) -> None:
    regime_info["regime_price_adjustment"] = True
    regime_info["adjustment_factor"] = round(adj_factor, 3)


def _counter_regime(
    daily: Any,
    regime_info: dict[str, Any],
    predictions: list[ForecastPoint],
    trend: str,
    current_price: float,
    ctx: MarketContext | None,
    days_ahead: int,
) -> str:
    predicted_change_pct = (
        (predictions[-1]["price"] - current_price) / current_price * 100 if current_price > 0 and predictions else 0.0
    )
    confident = daily.confidence > 0.6
    if confident and daily.dominant_regime in ("bearish", "top") and predicted_change_pct > 0 and predictions and ctx:
        adj_factor = at.regime_adjustment_factor(ctx, daily.dominant_regime, daily.confidence, predicted_change_pct)
        if trend != "bullish":
            adj_factor *= 0.6
        _dampen(predictions, current_price, adj_factor)
        trend = _reclassified_trend(predictions, current_price, ctx, days_ahead)
        _mark_adjusted(regime_info, adj_factor)
    elif (
        confident
        and daily.dominant_regime in ("bullish", "bottom")
        and predicted_change_pct < 0
        and predictions
        and ctx
    ):
        adj_factor = (
            at.regime_adjustment_factor(ctx, daily.dominant_regime, daily.confidence, predicted_change_pct) * 0.5
        )
        _dampen(predictions, current_price, adj_factor)
        _mark_adjusted(regime_info, adj_factor)
    return trend


def _bearish_drift(
    daily: Any,
    predictions: list[ForecastPoint],
    trend: str,
    current_price: float,
    ctx: MarketContext | None,
    days_ahead: int,
) -> str:
    if not (
        daily.confidence > 0.5
        and daily.dominant_regime in ("bearish", "top")
        and ctx
        and ctx.momentum_30d < -0.05
        and predictions
    ):
        return trend
    daily_drift = at.bearish_drift_factor(ctx)
    drift_scale = min(1.0, daily.confidence * 1.2)
    for i, pred in enumerate(predictions):
        drift_multiplier = 1.0 - daily_drift * drift_scale * (i + 1)
        pred["price"] = smart_round(pred["price"] * drift_multiplier)
        pred["confidence_low"] = smart_round(pred["confidence_low"] * drift_multiplier)
        pred["confidence_high"] = smart_round(pred["confidence_high"] * drift_multiplier)
    if predictions:
        return _reclassified_trend(predictions, current_price, ctx, days_ahead)
    return trend


def apply_regime(
    mtf: dict[str, Any],
    predictions: list[ForecastPoint],
    trend: str,
    current_price: float,
    ctx: MarketContext | None,
    days_ahead: int,
) -> tuple[dict[str, Any], str]:
    """Contexte de régime multi-horizon et corrections qu'il impose à la prévision : un régime contraire à plus de
    60 % de confiance rapproche la trajectoire du cours actuel (le régime lit sept indicateurs, l'ensemble surtout
    les prix, donc pas de double comptage), un marché baissier à momentum 30 j sous -5 % ajoute une dérive
    quotidienne, et l'incertitude du régime ou un désaccord quotidien/hebdomadaire élargit l'intervalle."""
    daily = mtf["daily"]
    regime_info: dict[str, Any] = {
        "dominant_regime": daily.dominant_regime,
        "confidence": daily.confidence,
        "probabilities": daily.probabilities,
        "timeframe_alignment": mtf.get("timeframe_alignment", "unknown"),
        "weekly_regime": mtf["weekly"].dominant_regime if mtf.get("weekly") else None,
        "note": mtf.get("note", ""),
    }
    trend = _counter_regime(daily, regime_info, predictions, trend, current_price, ctx, days_ahead)
    trend = _bearish_drift(daily, predictions, trend, current_price, ctx, days_ahead)

    ci_widen = at.ci_widening_factor(ctx, daily.dominant_regime, daily.confidence) if ctx else 0.05
    if ci_widen > 0.01:
        widen_intervals(predictions, ci_widen)
    if mtf.get("timeframe_alignment") == "divergent":
        widen_intervals(predictions, 0.05)
    return regime_info, trend


def apply_liquidity(volumes: list[float] | None, predictions: list[ForecastPoint]) -> str | None:
    """Sous 1 M EUR de volume moyen sur 7 jours, avertit d'un slippage probable et élargit l'intervalle de 5 à 25 %."""
    if not (volumes and len(volumes) >= 1):
        return None
    avg_recent_volume = float(np.mean(volumes[-7:])) if len(volumes) >= 7 else float(volumes[-1])
    if avg_recent_volume < ILLIQUID_VOLUME:
        liquidity_factor = max(0.05, min(0.25, 1.0 - avg_recent_volume / ILLIQUID_VOLUME))
        widen_intervals(predictions, liquidity_factor)
        return (
            f"Faible liquidité — volume moyen 7j: {avg_recent_volume:,.0f} EUR. "
            "Slippage probable sur les ordres importants."
        )
    return None


def clamp_intervals(predictions: list[ForecastPoint]) -> None:
    for pred in predictions:
        pred["confidence_low"] = min(pred["confidence_low"], pred["price"])
        pred["confidence_high"] = max(pred["confidence_high"], pred["price"])


def with_liquidity_warning(regime_info: dict[str, Any] | None, warning: str | None) -> dict[str, Any] | None:
    if warning and regime_info:
        regime_info["liquidity_warning"] = warning
        return regime_info
    if warning:
        return {
            "dominant_regime": "neutral",
            "confidence": 0.0,
            "probabilities": {},
            "timeframe_alignment": "unknown",
            "weekly_regime": None,
            "note": "",
            "liquidity_warning": warning,
        }
    return regime_info
