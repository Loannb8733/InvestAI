from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext


def compute_trend(
    current_price: float,
    final_predicted: float,
    historical: list[float],
    days_ahead: int = 7,
    ctx: MarketContext | None = None,
) -> tuple[str, float]:
    """Sens et force (0-100) de la tendance : variation prévue pondérée par l'élan des 5 derniers points."""
    if current_price == 0:
        return "neutral", 0.0
    pct_change = (final_predicted - current_price) / current_price * 100
    if len(historical) >= 5:
        recent_momentum = (historical[-1] - historical[-5]) / historical[-5] * 100
        combined = pct_change * 0.6 + recent_momentum * 0.4
    else:
        combined = pct_change
    threshold = at.trend_significance_threshold(ctx, days_ahead) if ctx else 2.0
    strength_scale = at.trend_strength_scale(ctx, days_ahead) if ctx else 0.2
    if combined > threshold:
        trend = "bullish"
    elif combined < -threshold:
        trend = "bearish"
    else:
        trend = "neutral"
    strength = min(100.0, abs(combined) / max(strength_scale, 0.01) * 50)
    return trend, strength
