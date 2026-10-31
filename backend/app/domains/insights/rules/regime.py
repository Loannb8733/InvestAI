"""Conseil tiré du régime de marché dominant."""

from collections.abc import Callable

from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight
from app.ml.regime_detector import RegimeResult

_MIN_PROBABILITY = 0.30
_CONFIRMED_PROBABILITY = 0.55
_SPECULATION_WARNING_PROBABILITY = 0.60


def _bearish(probability: float) -> SmartInsight:
    confirmed = probability > _CONFIRMED_PROBABILITY
    actions = [
        {"type": "hold", "symbol": "PORTFOLIO", "reason": "Reduire l'exposition aux actifs risques"},
        {"type": "hold", "symbol": "CASH", "reason": "Constituer une reserve cash (20-30%)"},
    ]
    if probability > _SPECULATION_WARNING_PROBABILITY:
        actions.append(
            {"type": "sell", "symbol": "PORTFOLIO", "reason": "Eviter le levier et les positions speculatives"}
        )
    return SmartInsight(
        category=InsightCategory.RISK,
        severity=InsightSeverity.CRITICAL if confirmed else InsightSeverity.WARNING,
        title="Marche baissier confirme" if confirmed else "Tendance baissiere detectee",
        message=(
            f"Le marche est en regime baissier ({probability * 100:.0f}% de probabilite). "
            "Reduisez l'exposition aux actifs risques, "
            "constituez une reserve de liquidites (20-30% du portefeuille), "
            "evitez le levier et les achats impulsifs. "
            "Privilegiez le DCA progressif si vous souhaitez accumuler."
        ),
        metric_name="market_regime",
        current_value=probability,
        actions=actions,
    )


def _bottom(probability: float) -> SmartInsight:
    return SmartInsight(
        category=InsightCategory.OPPORTUNITY,
        severity=InsightSeverity.INFO,
        title="Creux potentiel detecte",
        message=(
            f"Le marche montre des signes de creux ({probability * 100:.0f}%). "
            "Cela pourrait etre une zone d'accumulation si votre horizon est long terme. "
            "DCA recommande — ne tentez pas de timer le bottom exact."
        ),
        metric_name="market_regime",
        current_value=probability,
        actions=[{"type": "buy", "symbol": "PORTFOLIO", "reason": "Zone d'accumulation potentielle via DCA"}],
    )


def _bullish(probability: float) -> SmartInsight:
    return SmartInsight(
        category=InsightCategory.OPPORTUNITY,
        severity=InsightSeverity.INFO,
        title="Marche haussier",
        message=(
            f"Le marche est en tendance haussiere ({probability * 100:.0f}%). "
            "Conditions favorables pour vos positions. "
            "Preparez vos niveaux de prise de profits."
        ),
        metric_name="market_regime",
        current_value=probability,
    )


def _top(probability: float) -> SmartInsight:
    return SmartInsight(
        category=InsightCategory.RISK,
        severity=InsightSeverity.CRITICAL if probability > _CONFIRMED_PROBABILITY else InsightSeverity.WARNING,
        title="Sommet potentiel detecte",
        message=(
            f"Le marche montre des signes de surchauffe ({probability * 100:.0f}%). "
            "Prenez des profits partiels (20-30%), "
            "renforcez vos stop-loss et evitez les achats impulsifs."
        ),
        metric_name="market_regime",
        current_value=probability,
        actions=[
            {"type": "sell", "symbol": "PORTFOLIO", "reason": "Prendre des profits partiels"},
            {"type": "hold", "symbol": "PORTFOLIO", "reason": "Renforcer les stop-loss"},
        ],
    )


_BUILDERS: dict[str, Callable[[float], SmartInsight]] = {
    "bearish": _bearish,
    "bottom": _bottom,
    "bullish": _bullish,
    "top": _top,
}


def regime_insight(regime: RegimeResult) -> SmartInsight | None:
    """Conseil du régime dominant ; rien sous 30 % de probabilité ou pour un régime sans conseil."""
    probability = regime.probabilities.get(regime.dominant_regime, 0)
    builder = _BUILDERS.get(regime.dominant_regime)
    if probability < _MIN_PROBABILITY or builder is None:
        return None
    return builder(probability)
