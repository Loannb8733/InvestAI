"""Seuils calculés à partir du contexte de marché de chaque actif, à la place de constantes fixes."""

import math
from typing import Any

import numpy as np

from app.ml.market_context import MarketContext

CYCLE_ZONES = {"bottom": (0, 15), "bullish": (25, 60), "top": (60, 82), "bearish": (82, 100)}
CYCLE_PULL = {
    ("bearish", "bottom"): -5,
    ("bearish", "top"): +3,
    ("bearish", "bullish"): -2,
    ("bottom", "bearish"): +5,
    ("bottom", "bullish"): -3,
    ("bullish", "bottom"): +3,
    ("bullish", "top"): -3,
    ("top", "bullish"): +3,
    ("top", "bearish"): -3,
}


def rsi_thresholds(ctx: MarketContext) -> tuple[float, float]:
    """Surachat et survente : percentiles 90 et 10 du RSI de l'actif."""
    return ctx.rsi_history_p90, ctx.rsi_history_p10


def rsi_midpoints(ctx: MarketContext) -> tuple[float, float]:
    """Bornes de la zone neutre du RSI, à mi-chemin entre 50 et les seuils extrêmes."""
    ob, os = rsi_thresholds(ctx)
    return 50 + (ob - 50) * 0.5, 50 - (50 - os) * 0.5


def macd_signal_scaling(ctx: MarketContext) -> float:
    """Facteur qui donne une force de 0,5 à un histogramme MACD d'un écart-type quotidien ; 50 sans volatilité."""
    if ctx.daily_vol > 0:
        return 0.5 / ctx.daily_vol
    return 50.0


def bollinger_thresholds(ctx: MarketContext) -> tuple[float, float, float, float]:
    """Seuils de position dans les bandes, écartés vers l'extérieur quand la volatilité est haute."""
    vol_adj = np.clip(ctx.vol_percentile / 100, 0.3, 1.0)
    extreme_high = 0.90 + 0.08 * vol_adj
    high = 0.60 + 0.10 * vol_adj
    low = 0.40 - 0.10 * vol_adj
    extreme_low = 0.10 - 0.08 * vol_adj
    return float(extreme_high), float(high), float(low), float(extreme_low)


def ma_cross_significance(ctx: MarketContext) -> float:
    """Écart significatif entre moyennes mobiles, en % : un écart-type sur 20 jours, borné entre 1 et 15."""
    sig = ctx.daily_vol * math.sqrt(20) * 100
    return max(1.0, min(15.0, sig))


def momentum_thresholds(ctx: MarketContext) -> tuple[float, float, float, float]:
    """Seuils de variation en % tirés des percentiles 90 et 10 de l'élan de l'actif."""
    strong_bull = ctx.momentum_history_p90
    bull = ctx.momentum_history_p90 * 0.3
    bear = ctx.momentum_history_p10 * 0.3
    strong_bear = ctx.momentum_history_p10
    return strong_bull, bull, bear, strong_bear


def volatility_regime_thresholds(ctx: MarketContext) -> tuple[float, float]:
    """Volatilité annualisée extrême et élevée, en %, tirée de la distribution propre de l'actif."""
    ann = ctx.annualization_factor
    extreme = ctx.vol_history_p90 * math.sqrt(ann) * 100
    high = (ctx.vol_history_p90 + ctx.vol_history_p10) / 2 * math.sqrt(ann) * 100
    return float(extreme), float(high)


def fear_greed_thresholds(ctx: MarketContext) -> tuple[float, float, float, float]:
    """Seuils standard du Fear & Greed, abaissés côté avidité quand la volatilité est haute."""
    vol_adj = np.clip((ctx.vol_percentile - 50) / 100, -0.1, 0.1)
    return (
        float(75 - vol_adj * 50),
        float(55 - vol_adj * 25),
        float(45 + vol_adj * 25),
        float(25 + vol_adj * 50),
    )


def phase_spillover_weights(ctx: MarketContext) -> dict[str, float]:
    """Part des votes reportée sur les phases voisines, plus grande quand la volatilité est haute."""
    vol_factor = 1 + np.clip((ctx.vol_percentile - 50) / 100, -0.5, 0.5)
    return {
        "adjacent": round(0.10 * vol_factor + 0.05, 3),
        "opposite": round(0.10 * vol_factor * 0.7, 3),
        "diagonal": round(0.10 * vol_factor + 0.10, 3),
    }


def confidence_weights(ctx: MarketContext) -> tuple[float, float, float]:
    """Poids des indicateurs, de la longueur d'historique et de l'écart des probabilités dans la confiance."""
    if ctx.vol_percentile > 75:
        return 0.35, 0.40, 0.25
    if ctx.vol_percentile < 25:
        return 0.45, 0.25, 0.30
    return 0.40, 0.30, 0.30


def regime_adjustment_factor(
    ctx: MarketContext,
    regime: str,
    regime_confidence: float,
    predicted_change_pct: float,
) -> float:
    """Force de la correction d'une prévision par le régime, entre 0,05 et 0,95.

    Elle croît quand la volatilité courte dépasse la longue et quand la prévision contredit l'élan.
    """
    vol_ratio = ctx.realized_vol_7d / max(ctx.realized_vol_90d, 1e-8)
    divergence = abs(predicted_change_pct / 100 - ctx.momentum_30d) / max(ctx.daily_vol, 1e-8)
    base = {"bearish": 0.55, "top": 0.50, "bottom": 0.40, "bullish": 0.25}.get(regime, 0.30)
    adjusted = base * vol_ratio * (0.3 + 0.7 * min(1.0, divergence / 2))
    return float(np.clip(adjusted * regime_confidence, 0.05, 0.95))


def bearish_drift_factor(ctx: MarketContext) -> float:
    """Dérive baissière quotidienne : 20 % de la volatilité quotidienne, au moins 0,1 %."""
    return max(0.001, ctx.daily_vol * 0.2)


def trend_significance_threshold(ctx: MarketContext, horizon_days: int) -> float:
    """Variation en % qui rend une tendance significative : 0,2 écart-type par racine de jour, entre 0,3 et 6."""
    sig = ctx.daily_vol * 0.2 * math.sqrt(max(1, horizon_days)) * 100
    return float(np.clip(sig, 0.3, 6.0))


def trend_strength_scale(ctx: MarketContext, horizon_days: int) -> float:
    """Diviseur de la force de tendance : deux seuils de significativité valent une force de 100."""
    threshold = trend_significance_threshold(ctx, horizon_days)
    return max(0.01, threshold * 2)


def ci_widening_factor(
    ctx: MarketContext,
    regime: str,
    regime_confidence: float,
) -> float:
    """Élargissement de l'intervalle selon la volatilité, plus fort en sommet et en marché baissier."""
    base = 0.05
    vol_factor = ctx.vol_percentile / 100
    if regime in ("top", "bearish"):
        return float(base + 0.10 * vol_factor * regime_confidence)
    return float(base * vol_factor)


def ci_floor(ctx: MarketContext, horizon_days: int) -> float:
    """Demi-largeur minimale de l'intervalle, en fraction du prix, par type d'actif et racine du nombre de jours."""
    base = {"crypto": 0.03, "stock": 0.01, "etf": 0.008}.get(ctx.asset_type, 0.015)
    return base * math.sqrt(max(1, horizon_days))


def cycle_position(ctx: MarketContext, regime_probs: dict[str, float] | None = None) -> float:
    """Position de 0 à 100 dans le cycle (creux, accumulation, expansion, distribution, marché baissier).

    La phase dominante fixe la zone, la phase secondaire et le Fear & Greed affinent la position.
    """
    if not regime_probs:
        return 50.0
    sorted_regimes = sorted(regime_probs.items(), key=lambda x: x[1], reverse=True)
    dominant, dominant_prob = sorted_regimes[0]
    secondary = sorted_regimes[1][0] if len(sorted_regimes) > 1 else dominant
    secondary_prob = sorted_regimes[1][1] if len(sorted_regimes) > 1 else 0
    zone_lo, zone_hi = CYCLE_ZONES.get(dominant, (40, 60))
    confidence_factor = min(1.0, dominant_prob / 0.5)
    base_pos = zone_lo + (zone_hi - zone_lo) * 0.5 * confidence_factor
    base_pos += CYCLE_PULL.get((dominant, secondary), 0) * secondary_prob
    if ctx.fear_greed is not None:
        fg_adj = ((ctx.fear_greed - 50) / 50) * 5
        if dominant in ("bearish", "top"):
            base_pos -= fg_adj
        else:
            base_pos += fg_adj
    return float(np.clip(base_pos, 0, 100))


def correlation_thresholds(ctx: MarketContext | None = None) -> tuple[float, float]:
    """Corrélations forte positive et négative, relevées quand la volatilité est haute."""
    if ctx and ctx.vol_percentile > 75:
        return 0.80, -0.25
    return 0.70, -0.30


def concentration_thresholds() -> tuple[float, float]:
    """Indice de concentration (HHI) d'alerte et critique."""
    return 0.25, 0.40


def beta_classification(beta: float) -> str:
    """Catégorie de risque d'un bêta, de « inverse » à « very_aggressive »."""
    if beta > 1.5:
        return "very_aggressive"
    if beta > 1.0:
        return "aggressive"
    if beta > 0.8:
        return "neutral"
    if beta > 0.3:
        return "defensive"
    if beta > -0.1:
        return "very_defensive"
    return "inverse"


def anomaly_zscore_threshold(ctx: MarketContext) -> float:
    """Z-score d'anomalie, relevé quand la distribution a des queues épaisses."""
    kurtosis_adj = min(1.5, max(0, ctx.kurtosis * 0.1))
    return 2.5 + kurtosis_adj


def anomaly_price_threshold(ctx: MarketContext) -> float:
    """Variation de prix anormale en % : trois écarts-types mensuels, au moins 5."""
    monthly_vol = ctx.realized_vol_30d * math.sqrt(30)
    return float(max(5.0, monthly_vol * 3 * 100))


def sharpe_classification() -> tuple[float, float, float, float]:
    """Seuils conventionnels du ratio de Sharpe : excellent, bon, moyen, faible."""
    return 1.5, 1.0, 0.5, 0.0


def volatility_warning_thresholds(
    ctx: MarketContext | None = None,
) -> tuple[float, float]:
    """Volatilité annualisée d'alerte et extrême, en %, selon la distribution de l'actif ; 50 et 80 sans contexte."""
    if ctx:
        ann = ctx.annualization_factor
        high = ctx.vol_history_p90 * math.sqrt(ann) * 100 * 0.8
        extreme = ctx.vol_history_p90 * math.sqrt(ann) * 100 * 1.3
        return float(max(20, high)), float(max(40, extreme))
    return 50.0, 80.0


def var_warning_thresholds() -> tuple[float, float]:
    """VaR d'alerte et critique, en fraction."""
    return 0.10, 0.15


def build_display_thresholds(ctx: MarketContext | None = None) -> dict[str, Any]:
    """Seuils envoyés au frontend, qui ne garde pas les siens."""
    if ctx:
        fg: tuple[float, ...] = fear_greed_thresholds(ctx)
        sig = trend_significance_threshold(ctx, 7)
        vol_ext, vol_high = volatility_regime_thresholds(ctx)
    else:
        fg = (75, 55, 45, 25)
        sig = 2.0
        vol_ext, vol_high = 80, 50
    return {
        "fear_greed": {
            "extreme_greed": round(fg[0]),
            "greed": round(fg[1]),
            "fear": round(fg[2]),
            "extreme_fear": round(fg[3]),
        },
        "trend_strength": {"strong": round(sig * 2, 1), "moderate": round(sig, 1)},
        "prediction_score": {"good": 70, "poor": 45},
        "sharpe": {"excellent": 1.5, "good": 1.0, "fair": 0.5, "neutral": 0.0},
        "volatility": {"low": round(vol_high * 0.6, 1), "high": round(vol_high, 1), "extreme": round(vol_ext, 1)},
        "diversification": {"good": 60, "poor": 40},
        "beta": {"high": 1.0, "low": 0.5},
        "correlation": {
            "strong_positive": 0.7,
            "moderate_positive": 0.4,
            "moderate_negative": -0.3,
            "strong_negative": -0.5,
        },
    }
