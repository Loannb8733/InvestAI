"""Conseil tiré du ratio de Sharpe."""

from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight
from app.ml import adaptive_thresholds as adaptive_th


def sharpe_insights(sharpe: float) -> list[SmartInsight]:
    """Un conseil selon la classe du ratio de Sharpe."""
    excellent, good, fair, poor = adaptive_th.sharpe_classification()
    if sharpe < poor:
        return [
            SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.CRITICAL,
                title="Performance très faible",
                message=(
                    f"Votre ratio de Sharpe ({sharpe:.2f}) est négatif. "
                    "Votre portfolio sous-performe un placement sans risque."
                ),
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=good,
                potential_improvement="Diversifiez vers des actifs moins corrélés ou réduisez les positions perdantes.",
            )
        ]
    if sharpe < fair:
        return [
            SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.WARNING,
                title="Performance à améliorer",
                message=(
                    f"Votre ratio de Sharpe ({sharpe:.2f}) est faible. "
                    "Le rendement ne compense pas suffisamment le risque pris."
                ),
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=good,
                potential_improvement=f"Ciblez un Sharpe > {good} via une meilleure allocation.",
            )
        ]
    if sharpe < good:
        return [
            SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.INFO,
                title="Performance correcte",
                message=f"Votre ratio de Sharpe ({sharpe:.2f}) est acceptable mais peut être optimisé.",
                metric_name="sharpe_ratio",
                current_value=sharpe,
                target_value=excellent,
            )
        ]
    return [
        SmartInsight(
            category=InsightCategory.PERFORMANCE,
            severity=InsightSeverity.INFO,
            title="Excellente performance",
            message=(
                f"Votre ratio de Sharpe ({sharpe:.2f}) est excellent. Votre rendement ajusté au risque est très bon."
            ),
            metric_name="sharpe_ratio",
            current_value=sharpe,
        )
    ]
