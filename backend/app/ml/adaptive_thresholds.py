"""Adaptive Thresholds — data-driven replacements for hardcoded magic numbers.

Every function here takes a MarketContext and returns threshold(s) that
were previously hardcoded constants.  This makes the entire ML pipeline
self-calibrating: thresholds adapt to each asset's volatility, distribution,
and current market conditions.
"""

import math
from typing import Dict, Optional, Tuple

import numpy as np

from app.ml.market_context import MarketContext

# ═══════════════════════════════════════════════════════════════════════════
# A) Regime Detection Thresholds
# ═══════════════════════════════════════════════════════════════════════════


def rsi_thresholds(ctx: MarketContext) -> Tuple[float, float]:
    """Return (overbought, oversold) RSI thresholds for this asset.

    Uses p90/p10 of the asset's own RSI history instead of fixed 80/20.
    This means a high-beta crypto that regularly reaches RSI 85 won't
    trigger overbought at 70, while a low-vol ETF will.
    """
    return ctx.rsi_history_p90, ctx.rsi_history_p10


def rsi_midpoints(ctx: MarketContext) -> Tuple[float, float]:
    """Return (bullish_upper, bearish_lower) RSI midpoint thresholds.

    Instead of hardcoded 60/40, interpolates between 50 and the
    overbought/oversold thresholds.
    """
    ob, os = rsi_thresholds(ctx)
    bullish_upper = 50 + (ob - 50) * 0.5
    bearish_lower = 50 - (50 - os) * 0.5
    return bullish_upper, bearish_lower


def macd_signal_scaling(ctx: MarketContext) -> float:
    """Return factor to convert MACD histogram to 0-1 strength.

    Instead of hardcoded ``abs(histogram) * 50``, normalizes by the
    asset's daily volatility so that a 1-sigma MACD move ≈ strength 0.5.
    """
    if ctx.daily_vol > 0:
        return 0.5 / ctx.daily_vol
    return 50.0  # fallback: original behavior


def bollinger_thresholds(ctx: MarketContext) -> Tuple[float, float, float, float]:
    """Return (extreme_high, high, low, extreme_low) Bollinger position thresholds.

    In high-vol regimes, price touches band extremes more often,
    so we relax thresholds (push outward).  In low-vol, we tighten.
    """
    # vol_percentile 0-100 → vol_adj 0.3-1.0
    vol_adj = np.clip(ctx.vol_percentile / 100, 0.3, 1.0)
    extreme_high = 0.90 + 0.08 * vol_adj
    high = 0.60 + 0.10 * vol_adj
    low = 0.40 - 0.10 * vol_adj
    extreme_low = 0.10 - 0.08 * vol_adj
    return float(extreme_high), float(high), float(low), float(extreme_low)


def ma_cross_significance(ctx: MarketContext) -> float:
    """Return the % MA cross divergence that counts as significant.

    Instead of hardcoded 3%.  A significant cross = one that exceeds
    the noise level, defined as 1σ over 20 trading days.
    """
    sig = ctx.daily_vol * math.sqrt(20) * 100  # in percent
    return max(1.0, min(15.0, sig))  # clamp to [1%, 15%]


def momentum_thresholds(ctx: MarketContext) -> Tuple[float, float, float, float]:
    """Return (strong_bull, bull, bear, strong_bear) ROC thresholds in %.

    Uses p90/p10 of the asset's own momentum distribution instead of
    hardcoded 10/3/-3/-10%.
    """
    strong_bull = ctx.momentum_history_p90
    bull = ctx.momentum_history_p90 * 0.3
    bear = ctx.momentum_history_p10 * 0.3
    strong_bear = ctx.momentum_history_p10
    return strong_bull, bull, bear, strong_bear


def volatility_regime_thresholds(ctx: MarketContext) -> Tuple[float, float]:
    """Return (extreme_vol, high_vol) annualized volatility thresholds.

    Uses the asset's own vol distribution instead of hardcoded 80/50%.
    """
    ann = ctx.annualization_factor
    extreme = ctx.vol_history_p90 * math.sqrt(ann) * 100
    high = (ctx.vol_history_p90 + ctx.vol_history_p10) / 2 * math.sqrt(ann) * 100
    return float(extreme), float(high)


def fear_greed_thresholds(ctx: MarketContext) -> Tuple[float, float, float, float]:
    """Return (extreme_greed, greed, fear, extreme_fear) F&G thresholds.

    The F&G index is already normalized 0-100 across the whole market.
    We keep standard breakpoints but adjust slightly by vol regime:
    in high-vol, greed kicks in earlier (lower threshold) because
    euphoria in volatile markets is more dangerous.
    """
    vol_adj = np.clip((ctx.vol_percentile - 50) / 100, -0.1, 0.1)
    return (
        float(75 - vol_adj * 50),  # extreme_greed: 70-80
        float(55 - vol_adj * 25),  # greed: 52-58
        float(45 + vol_adj * 25),  # fear: 42-48
        float(25 + vol_adj * 50),  # extreme_fear: 20-30
    )


def phase_spillover_weights(ctx: MarketContext) -> Dict[str, float]:
    """Return vote spillover weights for adjacent market phases.

    Higher volatility → more regime uncertainty → more spillover to
    neighboring phases.
    """
    vol_factor = 1 + np.clip((ctx.vol_percentile - 50) / 100, -0.5, 0.5)
    return {
        "adjacent": round(0.10 * vol_factor + 0.05, 3),
        "opposite": round(0.10 * vol_factor * 0.7, 3),
        "diagonal": round(0.10 * vol_factor + 0.10, 3),
    }


def confidence_weights(ctx: MarketContext) -> Tuple[float, float, float]:
    """Return (indicator_w, data_w, spread_w) for confidence calculation.

    In high-vol markets, data length matters more (need more samples).
    In low-vol, indicators alone are often sufficient.
    """
    if ctx.vol_percentile > 75:
        return 0.35, 0.40, 0.25
    elif ctx.vol_percentile < 25:
        return 0.45, 0.25, 0.30
    return 0.40, 0.30, 0.30


# ═══════════════════════════════════════════════════════════════════════════
# B) Prediction Adjustment Factors
# ═══════════════════════════════════════════════════════════════════════════


def regime_adjustment_factor(
    ctx: MarketContext,
    regime: str,
    regime_confidence: float,
    predicted_change_pct: float,
) -> float:
    """Return adjustment strength for regime-aware prediction correction.

    Instead of hardcoded 0.7/0.6/0.5/0.3.  Derived from:
    - vol ratio (short vs long): increasing vol → stronger correction
    - momentum divergence: if prediction disagrees with momentum → trust regime more
    """
    vol_ratio = ctx.realized_vol_7d / max(ctx.realized_vol_90d, 1e-8)
    divergence = abs(predicted_change_pct / 100 - ctx.momentum_30d) / max(ctx.daily_vol, 1e-8)

    # Base strength depends on regime type (top/bottom are "turning point"
    # regimes where the model is most likely wrong)
    base = {"bearish": 0.55, "top": 0.50, "bottom": 0.40, "bullish": 0.25}.get(regime, 0.30)

    # Scale by conditions
    adjusted = base * vol_ratio * (0.3 + 0.7 * min(1.0, divergence / 2))
    return float(np.clip(adjusted * regime_confidence, 0.05, 0.95))


def bearish_drift_factor(ctx: MarketContext) -> float:
    """Return daily bearish drift as fraction of price.

    Instead of hardcoded 0.003.  Uses 20% of daily volatility.
    """
    return max(0.001, ctx.daily_vol * 0.2)


def trend_significance_threshold(ctx: MarketContext, horizon_days: int) -> float:
    """Return the % change required to classify as bullish/bearish.

    Instead of hardcoded 2%.  A move is significant if it exceeds
    0.3σ * √(horizon).  We use 0.3-sigma so that meaningful moves
    (e.g. -4% in 7 days for BTC) are classified directionally rather
    than swallowed by a too-wide neutral zone.
    """
    sig = ctx.daily_vol * 0.2 * math.sqrt(max(1, horizon_days)) * 100
    return float(np.clip(sig, 0.3, 6.0))  # clamp to [0.3%, 6%]


def trend_strength_scale(ctx: MarketContext, horizon_days: int) -> float:
    """Return the divisor for computing trend_strength 0-100.

    Instead of hardcoded ``abs(pct) * 5``.  Maps so that a 2σ move = 100.
    """
    threshold = trend_significance_threshold(ctx, horizon_days)
    return max(0.01, threshold * 2)  # 2σ = 100%


def ci_widening_factor(
    ctx: MarketContext,
    regime: str,
    regime_confidence: float,
) -> float:
    """Return CI widening factor for uncertain regimes.

    Instead of hardcoded 0.1/0.05.  Scales with vol regime.
    """
    base = 0.05
    vol_factor = ctx.vol_percentile / 100  # 0 to 1
    if regime in ("top", "bearish"):
        return float(base + 0.10 * vol_factor * regime_confidence)
    return float(base * vol_factor)


def xgboost_decay(ctx: MarketContext) -> float:
    """Return XGBoost prediction decay factor.

    Instead of hardcoded 0.95.  More conservative in high-vol markets.
    """
    return float(0.90 + 0.05 * (1 - ctx.vol_percentile / 100))


def ci_floor(ctx: MarketContext, horizon_days: int) -> float:
    """Return minimum CI half-width as fraction of price.

    Prevents false precision: crypto CIs should never be narrower than
    ~3% per sqrt(day), stocks ~1%, ETFs ~0.8%.
    """
    base = {"crypto": 0.03, "stock": 0.01, "etf": 0.008}.get(ctx.asset_type, 0.015)
    return base * math.sqrt(max(1, horizon_days))


def ci_safety_margin(ctx: MarketContext) -> float:
    """Return CI safety margin (fractional widening).

    Instead of hardcoded 0.05.  Wider for fat-tailed distributions.
    """
    kurt_factor = min(1.0, max(0, ctx.kurtosis) / 10)
    return float(0.02 + 0.06 * kurt_factor)


# ═══════════════════════════════════════════════════════════════════════════
# C) Cycle Position
# ═══════════════════════════════════════════════════════════════════════════


def cycle_position(ctx: MarketContext, regime_probs: Optional[dict] = None) -> float:
    """Return cycle position 0-100 representing the market cycle phase.

    The cycle goes clockwise:
      Creux (0-15) → Accumulation (15-40) → Expansion (40-65) →
      Distribution (65-85) → Euphorie/Bear (85-100)

    Strategy: use the dominant regime to set the zone, then refine
    position within that zone using secondary probabilities and context.
    """
    if not regime_probs:
        return 50.0

    # Sort regimes by probability (highest first)
    sorted_regimes = sorted(regime_probs.items(), key=lambda x: x[1], reverse=True)
    dominant = sorted_regimes[0][0]
    dominant_prob = sorted_regimes[0][1]
    secondary = sorted_regimes[1][0] if len(sorted_regimes) > 1 else dominant
    secondary_prob = sorted_regimes[1][1] if len(sorted_regimes) > 1 else 0

    # Zone ranges for each regime
    zone_map = {
        "bottom": (0, 15),  # Creux
        "bullish": (25, 60),  # Accumulation → Expansion
        "top": (60, 82),  # Distribution
        "bearish": (82, 100),  # Late-cycle bear
    }

    zone_lo, zone_hi = zone_map.get(dominant, (40, 60))

    # Position within zone: higher confidence → deeper into zone center
    # dominant_prob typically 0.3-0.7
    confidence_factor = min(1.0, dominant_prob / 0.5)  # normalize to 0-1
    base_pos = zone_lo + (zone_hi - zone_lo) * 0.5 * confidence_factor

    # Adjust based on which direction secondary regime pulls
    # Adjacent phases in cycle: bottom↔bullish, bullish↔top, top↔bearish, bearish↔bottom
    pull_toward = {
        ("bearish", "bottom"): -5,  # bear + bottom = late bear, moving toward creux
        ("bearish", "top"): +3,  # bear + top = early bear
        ("bearish", "bullish"): -2,
        ("bottom", "bearish"): +5,  # bottom + bear = early bottom
        ("bottom", "bullish"): -3,  # bottom + bull = late bottom, moving to accumulation
        ("bullish", "bottom"): +3,  # bull + bottom = early bull
        ("bullish", "top"): -3,  # bull + top = late bull
        ("top", "bullish"): +3,  # top + bull = early distribution
        ("top", "bearish"): -3,  # top + bear = late distribution
    }
    adj = pull_toward.get((dominant, secondary), 0) * secondary_prob
    base_pos += adj

    # Small F&G refinement (±5 max)
    if ctx.fear_greed is not None:
        fg_adj = ((ctx.fear_greed - 50) / 50) * 5  # -5 to +5
        # In bear zone, low F&G pushes higher (deeper bear); in bull zone, high F&G pushes lower
        if dominant in ("bearish", "top"):
            base_pos -= fg_adj  # low F&G → higher position (deeper bear)
        else:
            base_pos += fg_adj  # high F&G → lower position (deeper bull)

    return float(np.clip(base_pos, 0, 100))


# ═══════════════════════════════════════════════════════════════════════════
# D) Analytics Thresholds
# ═══════════════════════════════════════════════════════════════════════════


def correlation_thresholds(ctx: Optional[MarketContext] = None) -> Tuple[float, float]:
    """Return (strong_positive, negative) correlation thresholds.

    In high-vol regimes correlations spike, so we raise the bar.
    """
    if ctx and ctx.vol_percentile > 75:
        return 0.80, -0.25
    return 0.70, -0.30


def concentration_thresholds() -> Tuple[float, float]:
    """Return (warning, critical) HHI thresholds.

    Industry-standard portfolio construction limits.
    """
    return 0.25, 0.40


def beta_classification(beta: float) -> str:
    """Classify beta value into a risk category."""
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
    """Return Z-score threshold for anomaly detection.

    Instead of hardcoded 2.5/3.0.  Fat tails → need higher z-score
    to be truly anomalous (expected in heavy-tailed distributions).
    """
    kurtosis_adj = min(1.5, max(0, ctx.kurtosis * 0.1))
    return 2.5 + kurtosis_adj


def anomaly_price_threshold(ctx: MarketContext) -> float:
    """Return % threshold for price-change anomaly detection.

    Instead of hardcoded 20%/10%.  Uses 3σ of monthly returns.
    """
    monthly_vol = ctx.realized_vol_30d * math.sqrt(30)
    return float(max(5.0, monthly_vol * 3 * 100))


def sharpe_classification() -> Tuple[float, float, float, float]:
    """Return (excellent, good, fair, poor) Sharpe thresholds.

    These are financial convention, not data-dependent.
    """
    return 1.5, 1.0, 0.5, 0.0


def volatility_warning_thresholds(ctx: Optional[MarketContext] = None) -> Tuple[float, float]:
    """Return (high_pct, extreme_pct) annualized volatility warning thresholds.

    Adapted by asset type: crypto naturally has higher volatility.
    """
    if ctx:
        ann = ctx.annualization_factor
        # Use the asset's own vol distribution
        high = ctx.vol_history_p90 * math.sqrt(ann) * 100 * 0.8
        extreme = ctx.vol_history_p90 * math.sqrt(ann) * 100 * 1.3
        return float(max(20, high)), float(max(40, extreme))
    return 50.0, 80.0


def var_warning_thresholds() -> Tuple[float, float]:
    """Return (warning, critical) VaR thresholds as decimal."""
    return 0.10, 0.15


def sentiment_significance_threshold(ctx: MarketContext) -> float:
    """Return % change to classify an asset as bullish/bearish for sentiment.

    Instead of hardcoded ±1%.  Uses half of the trend significance threshold.
    """
    return trend_significance_threshold(ctx, 1) * 0.5


# ═══════════════════════════════════════════════════════════════════════════
# E) Display Thresholds (sent to frontend)
# ═══════════════════════════════════════════════════════════════════════════


def build_display_thresholds(ctx: Optional[MarketContext] = None) -> Dict:
    """Build thresholds dictionary to send to the frontend.

    The frontend reads these instead of hardcoding its own values.
    """
    if ctx:
        fg = fear_greed_thresholds(ctx)
        sig = trend_significance_threshold(ctx, 7)
        vol_ext, vol_high = volatility_regime_thresholds(ctx)
    else:
        fg = (75, 55, 45, 25)
        sig = 2.0
        vol_ext = 80
        vol_high = 50

    return {
        "fear_greed": {
            "extreme_greed": round(fg[0]),
            "greed": round(fg[1]),
            "fear": round(fg[2]),
            "extreme_fear": round(fg[3]),
        },
        "trend_strength": {
            "strong": round(sig * 2, 1),  # 2σ = strong
            "moderate": round(sig, 1),  # 1σ = moderate
        },
        "prediction_score": {
            "good": 70,
            "poor": 45,
        },
        "sharpe": {
            "excellent": 1.5,
            "good": 1.0,
            "fair": 0.5,
            "neutral": 0.0,
        },
        "volatility": {
            "low": round(vol_high * 0.6, 1),
            "high": round(vol_high, 1),
            "extreme": round(vol_ext, 1),
        },
        "diversification": {
            "good": 60,
            "poor": 40,
        },
        "beta": {
            "high": 1.0,
            "low": 0.5,
        },
        "correlation": {
            "strong_positive": 0.7,
            "moderate_positive": 0.4,
            "moderate_negative": -0.3,
            "strong_negative": -0.5,
        },
    }
