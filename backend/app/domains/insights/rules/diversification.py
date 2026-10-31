"""Conseils tirés de la concentration du portefeuille."""

from typing import Any

from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight
from app.ml import adaptive_thresholds as adaptive_th

_WELL_DIVERSIFIED_HHI = 0.10


def _top_holding_insights(top_holdings: list[dict[str, Any]]) -> list[SmartInsight]:
    if not top_holdings:
        return []
    warning, critical = adaptive_th.concentration_thresholds()
    weight = top_holdings[0].get("weight", 0)
    symbol = top_holdings[0].get("symbol", "?")
    if weight > critical:
        return [
            SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.CRITICAL,
                title="Concentration excessive",
                message=f"{symbol} représente {weight * 100:.0f}% de votre portfolio. C'est trop concentré.",
                metric_name="top_holding_weight",
                current_value=weight,
                target_value=warning,
                potential_improvement=f"Réduisez {symbol} à max {warning * 100:.0f}% et diversifiez.",
                actions=[{"type": "sell", "symbol": symbol, "reason": "Réduire la concentration"}],
            )
        ]
    if weight > warning:
        return [
            SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.WARNING,
                title="Concentration élevée",
                message=f"{symbol} représente {weight * 100:.0f}% de votre portfolio.",
                metric_name="top_holding_weight",
                current_value=weight,
                target_value=warning,
            )
        ]
    return []


def _hhi_insights(hhi: float) -> list[SmartInsight]:
    warning, _ = adaptive_th.concentration_thresholds()
    if hhi > warning:
        return [
            SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.WARNING,
                title="Portfolio peu diversifié",
                message=f"Votre indice HHI ({hhi:.2f}) indique une concentration élevée.",
                metric_name="hhi",
                current_value=hhi,
                target_value=0.15,
                potential_improvement="Ajoutez des actifs décorrélés (actions, ETF, or).",
            )
        ]
    if hhi < _WELL_DIVERSIFIED_HHI:
        return [
            SmartInsight(
                category=InsightCategory.DIVERSIFICATION,
                severity=InsightSeverity.INFO,
                title="Bonne diversification",
                message=f"Votre portfolio est bien diversifié (HHI: {hhi:.2f}).",
                metric_name="hhi",
                current_value=hhi,
            )
        ]
    return []


def diversification_insights(hhi: float | None, top_holdings: list[dict[str, Any]]) -> list[SmartInsight]:
    """Poids de la première ligne, puis HHI ; sans mesure du HHI, aucun verdict ne s'en déduit."""
    insights = _top_holding_insights(top_holdings)
    return insights if hhi is None else [*insights, *_hhi_insights(hhi)]
