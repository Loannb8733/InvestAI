"""Passage du rapport de santé à sa réponse HTTP."""

from dataclasses import asdict

from app.domains.insights.results import AnomalyImpact, PortfolioHealthReport, SmartInsight
from app.domains.insights.schemas import (
    ActionResponse,
    AnomalyImpactResponse,
    IndicatorSignalResponse,
    InsightResponse,
    MarketRegimeResponse,
    MetricsSummaryResponse,
    PortfolioHealthResponse,
    RebalancingOrderResponse,
    RegimeConfigResponse,
    RegimeResultResponse,
    RiskClusterResponse,
)
from app.ml.regime_detector import MarketRegime, RegimeResult


def _insight(insight: SmartInsight) -> InsightResponse:
    return InsightResponse(
        category=insight.category.value,
        severity=insight.severity.value,
        title=insight.title,
        message=insight.message,
        metric_name=insight.metric_name,
        current_value=insight.current_value,
        target_value=insight.target_value,
        potential_improvement=insight.potential_improvement,
        actions=[
            ActionResponse(
                type=action.get("type", ""),
                symbol=action.get("symbol", ""),
                amount_eur=action.get("amount_eur"),
                reason=action.get("reason"),
            )
            for action in insight.actions
        ],
    )


def anomaly_response(impact: AnomalyImpact) -> AnomalyImpactResponse:
    """Réponse d'une anomalie."""
    return AnomalyImpactResponse(
        symbol=impact.symbol,
        anomaly_type=impact.anomaly_type,
        severity=impact.severity,
        description=impact.description,
        price_change_percent=impact.price_change_percent,
        position_value_eur=impact.position_value_eur,
        impact_eur=impact.impact_eur,
        detected_at=impact.detected_at.isoformat() if impact.detected_at else "",
    )


def _regime_result(result: RegimeResult) -> RegimeResultResponse:
    return RegimeResultResponse(
        symbol=result.symbol,
        probabilities=result.probabilities,
        dominant_regime=result.dominant_regime,
        confidence=result.confidence,
        signals=[
            IndicatorSignalResponse(
                name=signal.name,
                value=signal.value,
                signal=signal.signal,
                strength=signal.strength,
                description=signal.description,
            )
            for signal in result.signals
        ],
        description=result.description,
    )


def _market_regime(regime: MarketRegime | None) -> MarketRegimeResponse | None:
    if regime is None:
        return None
    return MarketRegimeResponse(
        market=_regime_result(regime.market),
        per_asset=[_regime_result(result) for result in regime.per_asset],
        generated_at=regime.generated_at.isoformat(),
    )


def _metrics_summary(report: PortfolioHealthReport) -> MetricsSummaryResponse:
    metrics = report.metrics_summary
    config = metrics.get("regime_config")
    return MetricsSummaryResponse(
        sharpe_ratio=metrics.get("sharpe_ratio", 0),
        sortino_ratio=metrics.get("sortino_ratio", 0),
        volatility=metrics.get("volatility", 0),
        var_95=metrics.get("var_95", 0),
        max_drawdown=metrics.get("max_drawdown", 0),
        hhi=metrics.get("hhi", 0),
        total_value=metrics.get("total_value", 0),
        regime_config=RegimeConfigResponse(**config) if config else None,
        avg_top5_correlation=metrics.get("avg_top5_correlation"),
        risk_clusters=[RiskClusterResponse(**cluster) for cluster in (metrics.get("risk_clusters") or [])] or None,
    )


def health_response(report: PortfolioHealthReport) -> PortfolioHealthResponse:
    """Réponse complète du rapport de santé."""
    return PortfolioHealthResponse(
        overall_score=report.overall_score,
        overall_status=report.overall_status,
        insights=[_insight(insight) for insight in report.insights],
        rebalancing_orders=[RebalancingOrderResponse(**asdict(order)) for order in report.rebalancing_orders],
        anomaly_impacts=[anomaly_response(impact) for impact in report.anomaly_impacts],
        metrics_summary=_metrics_summary(report),
        market_regime=_market_regime(report.market_regime),
        generated_at=report.generated_at.isoformat(),
    )
