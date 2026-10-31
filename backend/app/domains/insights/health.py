"""Santé du portefeuille : métriques, conseils, rééquilibrage, anomalies et note globale."""

import logging
import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.results import PortfolioAnalytics
from app.domains.analytics.service import analytics_service
from app.domains.insights.anomalies import anomaly_impacts
from app.domains.insights.market_regime import detect_market_regime
from app.domains.insights.rebalancing import rebalancing_orders
from app.domains.insights.results import (
    AnomalyImpact,
    InsightCategory,
    InsightSeverity,
    PortfolioHealthReport,
    RebalancingOrder,
    SmartInsight,
)
from app.domains.insights.rules.correlation import correlation_insights
from app.domains.insights.rules.cross_asset import cross_asset_insights
from app.domains.insights.rules.diversification import diversification_insights
from app.domains.insights.rules.performance import sharpe_insights
from app.domains.insights.rules.regime import regime_insight
from app.domains.insights.rules.risk import risk_insights
from app.domains.insights.safe_haven import gold_exposure
from app.domains.insights.score import overall_score
from app.ml.regime_detector import MarketRegime

logger = logging.getLogger(__name__)

_TOP_HOLDINGS = 5
_TOP_ACTIONS = 3
_CROSS_ASSET_DAYS = 60
_SEVERITY_ORDER = {InsightSeverity.CRITICAL: 0, InsightSeverity.WARNING: 1, InsightSeverity.INFO: 2}


def _finite(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(number) or math.isinf(number) else number


def _unavailable_report() -> PortfolioHealthReport:
    return PortfolioHealthReport(
        overall_score=0,
        overall_status="unknown",
        insights=[
            SmartInsight(
                category=InsightCategory.PERFORMANCE,
                severity=InsightSeverity.WARNING,
                title="Analyse impossible",
                message="Impossible d'analyser le portfolio. Vérifiez que vous avez des actifs.",
            )
        ],
        rebalancing_orders=[],
        anomaly_impacts=[],
        metrics_summary={},
        generated_at=datetime.now(UTC),
    )


async def _concentration(
    db: AsyncSession, user_id: str, analytics: PortfolioAnalytics
) -> tuple[float | None, list[dict[str, Any]]]:
    try:
        diversification = await analytics_service.get_diversification_analysis(db, user_id)
        allocation = analytics.allocation_by_asset or {}
        top_holdings = [
            {"symbol": symbol, "weight": _finite(weight) / 100, "name": symbol}
            for symbol, weight in sorted(allocation.items(), key=lambda item: -item[1])[:_TOP_HOLDINGS]
        ]
        return _finite(diversification.get("concentration_risk", 0)), top_holdings
    except Exception:
        logger.warning("Analyse de diversification indisponible — HHI non mesuré", exc_info=True)
        return None, []


def _rebalancing_insight(orders: list[RebalancingOrder]) -> SmartInsight:
    return SmartInsight(
        category=InsightCategory.REBALANCING,
        severity=InsightSeverity.INFO,
        title="Optimisation possible",
        message=f"Un rééquilibrage de {len(orders)} positions pourrait améliorer votre ratio de Sharpe.",
        metric_name="positions_to_rebalance",
        current_value=len(orders),
        actions=[
            {"type": order.action, "symbol": order.symbol, "amount_eur": order.amount_eur, "reason": order.reason}
            for order in orders[:_TOP_ACTIONS]
        ],
    )


def _anomaly_insight(impact: AnomalyImpact) -> SmartInsight:
    return SmartInsight(
        category=InsightCategory.ANOMALY,
        severity=InsightSeverity.CRITICAL if impact.severity == "high" else InsightSeverity.WARNING,
        title=f"Anomalie détectée sur {impact.symbol}",
        message=f"{impact.description}. Impact: {impact.impact_eur:+,.0f}€ ({impact.price_change_percent:+.1f}%)",
        metric_name="impact_eur",
        current_value=impact.impact_eur,
    )


async def _correlation_figures(
    db: AsyncSession, user_id: str, days: int, top_holdings: list[dict[str, Any]]
) -> tuple[list[SmartInsight], float, list[dict[str, Any]] | None]:
    try:
        data = await analytics_service.get_correlation_matrix(db, user_id, days=days)
        return correlation_insights(data, top_holdings)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Correlation analysis failed: %s", exc)
        return [], 0.0, None


async def _cross_asset(
    db: AsyncSession, user_id: str, top_holdings: list[dict[str, Any]], market_regime: MarketRegime | None
) -> list[SmartInsight]:
    try:
        data = await analytics_service.get_correlation_matrix(db, user_id, days=_CROSS_ASSET_DAYS)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cross-asset correlation analysis failed: %s", exc)
        return []
    return cross_asset_insights(data, top_holdings, market_regime)


def _regime_config(market_regime: MarketRegime | None) -> dict[str, Any] | None:
    if market_regime is None:
        return None
    config = market_regime.config
    return {
        "risk_multiplier": config.risk_multiplier,
        "alpha_threshold": config.alpha_threshold,
        "gold_relevance": config.gold_relevance,
        "mode_label": config.mode_label,
        "vol_regime": config.vol_regime,
    }


async def portfolio_health(db: AsyncSession, user_id: str, days: int = 30) -> PortfolioHealthReport:
    """Rapport complet sur `days` jours ; métriques en fractions, sauf la VaR et le patrimoine en euros."""
    try:
        analytics = await analytics_service.get_user_analytics(db, user_id, days=days)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get analytics: %s", exc)
        return _unavailable_report()
    sharpe = _finite(analytics.sharpe_ratio)
    total_value = _finite(analytics.total_value)
    volatility = _finite(analytics.portfolio_volatility) / 100.0
    max_drawdown = abs(_finite(analytics.max_drawdown)) / 100.0
    var_95_eur = _finite(analytics.var_95)
    var_95 = var_95_eur / total_value if total_value > 0 else 0.0
    hhi, top_holdings = await _concentration(db, user_id, analytics)
    insights = [
        *sharpe_insights(sharpe),
        *risk_insights(volatility, var_95, max_drawdown),
        *diversification_insights(hhi, top_holdings),
    ]
    market_regime = await detect_market_regime(top_holdings, days)
    if market_regime and market_regime.market.dominant_regime != "unknown":
        from_regime = regime_insight(market_regime.market)
        if from_regime:
            insights.append(from_regime)
    orders = await rebalancing_orders(db, user_id, total_value, market_regime, days)
    if orders:
        insights.append(_rebalancing_insight(orders))
    impacts = await anomaly_impacts(db, user_id)
    insights.extend(_anomaly_insight(impact) for impact in impacts)
    from_correlation, avg_top5, clusters = await _correlation_figures(db, user_id, days, top_holdings)
    insights.extend(from_correlation)
    exposure = await gold_exposure(db, user_id, total_value)
    insights.extend(await _cross_asset(db, user_id, top_holdings, market_regime))
    score, status = overall_score(
        sharpe,
        volatility,
        var_95,
        hhi,
        len(impacts),
        max_drawdown=max_drawdown,
        gold_exposure=exposure,
        market_regime=market_regime,
        avg_top5_corr=avg_top5,
    )
    insights.sort(key=lambda insight: _SEVERITY_ORDER.get(insight.severity, 3))
    return PortfolioHealthReport(
        overall_score=score,
        overall_status=status,
        insights=insights,
        rebalancing_orders=orders,
        anomaly_impacts=impacts,
        metrics_summary={
            "sharpe_ratio": sharpe,
            "sortino_ratio": _finite(analytics.sortino_ratio),
            "volatility": volatility,
            "var_95": var_95_eur,
            "max_drawdown": max_drawdown,
            "hhi": hhi,
            "total_value": total_value,
            "regime_config": _regime_config(market_regime),
            "avg_top5_correlation": round(avg_top5, 3) if clusters is not None else None,
            "risk_clusters": clusters,
        },
        market_regime=market_regime,
        generated_at=datetime.now(UTC),
    )


async def dashboard_summary(db: AsyncSession, user_id: str, days: int = 30) -> dict[str, Any]:
    """Résumé du widget : note, premier conseil, distance au seuil de rentabilité, anomalies et régime."""
    report = await portfolio_health(db, user_id, days)
    top_insight = None
    if report.insights:
        best = report.insights[0]
        top_insight = {
            "title": best.title,
            "message": best.message,
            "severity": best.severity.value,
            "category": best.category.value,
        }
    total_value = report.metrics_summary.get("total_value", 0)
    breakeven_pct = None
    try:
        analytics = await analytics_service.get_user_analytics(db, user_id, days=days)
        if analytics.total_invested and analytics.total_invested > 0:
            breakeven_pct = round(((total_value / analytics.total_invested) - 1) * 100, 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Breakeven distance computation failed for dashboard summary: %s", exc)
    return {
        "health_score": report.overall_score,
        "health_status": report.overall_status,
        "top_insight": top_insight,
        "breakeven_pct": breakeven_pct,
        "anomaly_count": len(report.anomaly_impacts),
        "regime": report.market_regime.market.dominant_regime if report.market_regime else None,
        "generated_at": report.generated_at.isoformat(),
    }
