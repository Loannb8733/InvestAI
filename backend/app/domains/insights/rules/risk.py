"""Conseils tirés de la volatilité, de la VaR et du drawdown, exprimés en fractions."""

from app.domains.insights.results import InsightCategory, InsightSeverity, SmartInsight
from app.ml import adaptive_thresholds as adaptive_th

_SEVERE_DRAWDOWN = 0.25
_LARGE_DRAWDOWN = 0.15


def _volatility_insights(volatility: float) -> list[SmartInsight]:
    high, extreme = adaptive_th.volatility_warning_thresholds()
    if volatility > extreme / 100:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL,
                title="Volatilité extrême",
                message=f"Votre portfolio a une volatilité de {volatility * 100:.0f}%. C'est très risqué.",
                metric_name="volatility",
                current_value=volatility,
                target_value=0.30,
                potential_improvement=(
                    "Ajoutez des actifs stables (ETF obligataires, stablecoins) pour réduire la volatilité."
                ),
            )
        ]
    if volatility > high / 100:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="Volatilité élevée",
                message=(
                    f"Votre portfolio a une volatilité de {volatility * 100:.0f}%. "
                    "Préparez-vous à des variations importantes."
                ),
                metric_name="volatility",
                current_value=volatility,
                target_value=0.30,
            )
        ]
    return []


def _var_insights(var_95: float) -> list[SmartInsight]:
    warning, critical = adaptive_th.var_warning_thresholds()
    if var_95 > critical:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL,
                title="Risque de perte élevé",
                message=(
                    f"Votre VaR 95% est de {var_95 * 100:.1f}%. "
                    "Vous pouvez perdre cette proportion en une journée (5% de chance)."
                ),
                metric_name="var_95",
                current_value=var_95,
                target_value=0.05,
            )
        ]
    if var_95 > warning:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="VaR à surveiller",
                message=f"Votre VaR 95% est de {var_95 * 100:.1f}%. Le risque journalier est notable.",
                metric_name="var_95",
                current_value=var_95,
            )
        ]
    return []


def _drawdown_insights(max_drawdown: float) -> list[SmartInsight]:
    if max_drawdown > _SEVERE_DRAWDOWN:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL,
                title="Drawdown severe",
                message=(
                    f"Votre portfolio a subi une baisse de {max_drawdown * 100:.0f}% depuis son pic. "
                    "Reduisez l'exposition aux actifs les plus volatils et "
                    "constituez une reserve de liquidites."
                ),
                metric_name="max_drawdown",
                current_value=max_drawdown,
                target_value=0.15,
                potential_improvement="Diversifiez avec des actifs stables pour reduire le drawdown futur.",
            )
        ]
    if max_drawdown > _LARGE_DRAWDOWN:
        return [
            SmartInsight(
                category=InsightCategory.RISK,
                severity=InsightSeverity.WARNING,
                title="Drawdown important",
                message=f"Votre portfolio a subi une baisse de {max_drawdown * 100:.0f}% depuis son pic.",
                metric_name="max_drawdown",
                current_value=max_drawdown,
                target_value=0.10,
            )
        ]
    return []


def risk_insights(volatility: float, var_95: float, max_drawdown: float) -> list[SmartInsight]:
    """Conseils de risque, volatilité d'abord."""
    return [*_volatility_insights(volatility), *_var_insights(var_95), *_drawdown_insights(max_drawdown)]
