"""Note de santé du portefeuille, de 0 à 100."""

from app.ml import adaptive_thresholds as adaptive_th
from app.ml.regime_detector import MarketRegime

_MAX_ANOMALY_PENALTY = 20
_ANOMALY_PENALTY = 5
_DRAWDOWN_PENALTIES = ((0.40, 35), (0.25, 25), (0.15, 15), (0.10, 10))
_CORRELATION_PENALTIES = ((0.85, 15), (0.7, 10), (0.6, 5))
_MIN_GOLD_EXPOSURE = 0.05
_MAX_GOLD_BONUS = 10
_GOLD_MULTIPLIERS = {"high": 1.5, "medium": 1.0, "low": 0.5}
_DEFENSIVE_REGIMES = {"bearish", "markdown", "distribution", "bottom", "bottoming"}
_STATUSES = ((80, "excellent"), (65, "good"), (50, "fair"), (30, "poor"))


def _penalty_above(value: float, tiers: tuple[tuple[float, int], ...]) -> int:
    return next((penalty for threshold, penalty in tiers if value > threshold), 0)


def _sharpe_adjustment(sharpe: float) -> int:
    excellent, good, fair, poor = adaptive_th.sharpe_classification()
    if sharpe < poor:
        return -30
    if sharpe < fair:
        return -20
    if sharpe < good:
        return -10
    return 10 if sharpe > excellent else 0


def _risk_penalty(volatility: float, var_95: float, hhi: float | None) -> int:
    vol_high, vol_extreme = adaptive_th.volatility_warning_thresholds()
    var_warning, var_critical = adaptive_th.var_warning_thresholds()
    conc_warning, conc_critical = adaptive_th.concentration_thresholds()
    penalty = _penalty_above(volatility, ((vol_extreme / 100, 20), (vol_high / 100, 10)))
    penalty += _penalty_above(var_95, ((var_critical, 15), (var_warning, 10)))
    if hhi is not None:
        penalty += _penalty_above(hhi, ((conc_critical, 15), (conc_warning, 10)))
    return penalty


def _gold_bonus(gold_exposure: float, market_regime: MarketRegime | None) -> int:
    if gold_exposure <= _MIN_GOLD_EXPOSURE or market_regime is None:
        return 0
    if market_regime.market.dominant_regime not in _DEFENSIVE_REGIMES:
        return 0
    multiplier = _GOLD_MULTIPLIERS.get(market_regime.config.gold_relevance, 1.0)
    return min(_MAX_GOLD_BONUS, int(gold_exposure * 100 * multiplier))


def _status(score: int) -> str:
    return next((label for floor, label in _STATUSES if score >= floor), "critical")


def overall_score(
    sharpe: float,
    volatility: float,
    var_95: float,
    hhi: float | None,
    anomaly_count: int,
    max_drawdown: float = 0.0,
    gold_exposure: float = 0.0,
    market_regime: MarketRegime | None = None,
    avg_top5_corr: float = 0.0,
) -> tuple[int, str]:
    """Part de 100, retire les pénalités de risque, ajoute le bonus d'or en régime défensif ; rend note et statut."""
    score = 100 + _sharpe_adjustment(sharpe)
    score -= _risk_penalty(volatility, var_95, hhi)
    score -= min(anomaly_count * _ANOMALY_PENALTY, _MAX_ANOMALY_PENALTY)
    score -= _penalty_above(abs(max_drawdown), _DRAWDOWN_PENALTIES)
    score -= _penalty_above(avg_top5_corr, _CORRELATION_PENALTIES)
    score += _gold_bonus(gold_exposure, market_regime)
    clamped = max(0, min(100, score))
    return clamped, _status(clamped)
