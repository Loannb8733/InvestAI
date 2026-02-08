"""Smart Insights API endpoints."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.smart_insights_service import smart_insights_service

router = APIRouter()


# === Response Models ===

class ActionResponse(BaseModel):
    """A suggested action."""
    type: str  # buy, sell, hold
    symbol: str
    amount_eur: Optional[float] = None
    reason: Optional[str] = None


class InsightResponse(BaseModel):
    """A smart insight."""
    category: str
    severity: str
    title: str
    message: str
    metric_name: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    potential_improvement: Optional[str] = None
    actions: List[ActionResponse] = []


class RebalancingOrderResponse(BaseModel):
    """A rebalancing order suggestion."""
    symbol: str
    name: str
    action: str  # buy or sell
    current_weight: float
    target_weight: float
    current_value_eur: float
    target_value_eur: float
    amount_eur: float
    reason: str


class AnomalyImpactResponse(BaseModel):
    """An anomaly with EUR impact."""
    symbol: str
    anomaly_type: str
    severity: str
    description: str
    price_change_percent: float
    position_value_eur: float
    impact_eur: float
    detected_at: str


class MetricsSummaryResponse(BaseModel):
    """Summary of key metrics."""
    sharpe_ratio: float
    sortino_ratio: float
    volatility: float
    var_95: float
    max_drawdown: float
    hhi: float
    total_value: float


class IndicatorSignalResponse(BaseModel):
    """A single indicator signal."""
    name: str
    value: float
    signal: str
    strength: float
    description: str


class RegimeResultResponse(BaseModel):
    """Regime detection for a symbol."""
    symbol: str
    probabilities: Dict[str, float]
    dominant_regime: str
    confidence: float
    signals: List[IndicatorSignalResponse]
    description: str


class MarketRegimeResponse(BaseModel):
    """Market regime analysis."""
    market: RegimeResultResponse
    per_asset: List[RegimeResultResponse]
    generated_at: str


class PortfolioHealthResponse(BaseModel):
    """Complete portfolio health report."""
    overall_score: int
    overall_status: str
    insights: List[InsightResponse]
    rebalancing_orders: List[RebalancingOrderResponse]
    anomaly_impacts: List[AnomalyImpactResponse]
    metrics_summary: MetricsSummaryResponse
    market_regime: Optional[MarketRegimeResponse] = None
    generated_at: str


# === Helpers ===

def _build_regime_response(regime) -> Optional[MarketRegimeResponse]:
    """Convert MarketRegime dataclass to response model."""
    if regime is None:
        return None

    def _result_to_response(r) -> RegimeResultResponse:
        return RegimeResultResponse(
            symbol=r.symbol,
            probabilities=r.probabilities,
            dominant_regime=r.dominant_regime,
            confidence=r.confidence,
            signals=[
                IndicatorSignalResponse(
                    name=s.name,
                    value=s.value,
                    signal=s.signal,
                    strength=s.strength,
                    description=s.description,
                ) for s in r.signals
            ],
            description=r.description,
        )

    return MarketRegimeResponse(
        market=_result_to_response(regime.market),
        per_asset=[_result_to_response(r) for r in regime.per_asset],
        generated_at=regime.generated_at.isoformat(),
    )


# === Endpoints ===

@router.get("/health", response_model=PortfolioHealthResponse)
async def get_portfolio_health(
    days: int = Query(30, ge=7, le=365, description="Période d'analyse en jours"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioHealthResponse:
    """
    Analyse complète de la santé du portfolio.

    Retourne:
    - Score global (0-100)
    - Insights intelligents avec recommandations
    - Suggestions de rééquilibrage basées sur MPT
    - Anomalies détectées avec impact en EUR
    - Régime de marché (bearish/bottom/bullish/top)
    """
    report = await smart_insights_service.get_portfolio_health(
        db, str(current_user.id), days
    )

    return PortfolioHealthResponse(
        overall_score=report.overall_score,
        overall_status=report.overall_status,
        insights=[
            InsightResponse(
                category=i.category.value,
                severity=i.severity.value,
                title=i.title,
                message=i.message,
                metric_name=i.metric_name,
                current_value=i.current_value,
                target_value=i.target_value,
                potential_improvement=i.potential_improvement,
                actions=[
                    ActionResponse(
                        type=a.get("type", ""),
                        symbol=a.get("symbol", ""),
                        amount_eur=a.get("amount_eur"),
                        reason=a.get("reason"),
                    ) for a in i.actions
                ],
            ) for i in report.insights
        ],
        rebalancing_orders=[
            RebalancingOrderResponse(
                symbol=o.symbol,
                name=o.name,
                action=o.action,
                current_weight=o.current_weight,
                target_weight=o.target_weight,
                current_value_eur=o.current_value_eur,
                target_value_eur=o.target_value_eur,
                amount_eur=o.amount_eur,
                reason=o.reason,
            ) for o in report.rebalancing_orders
        ],
        anomaly_impacts=[
            AnomalyImpactResponse(
                symbol=a.symbol,
                anomaly_type=a.anomaly_type,
                severity=a.severity,
                description=a.description,
                price_change_percent=a.price_change_percent,
                position_value_eur=a.position_value_eur,
                impact_eur=a.impact_eur,
                detected_at=a.detected_at.isoformat() if a.detected_at else "",
            ) for a in report.anomaly_impacts
        ],
        metrics_summary=MetricsSummaryResponse(
            sharpe_ratio=report.metrics_summary.get("sharpe_ratio", 0),
            sortino_ratio=report.metrics_summary.get("sortino_ratio", 0),
            volatility=report.metrics_summary.get("volatility", 0),
            var_95=report.metrics_summary.get("var_95", 0),
            max_drawdown=report.metrics_summary.get("max_drawdown", 0),
            hhi=report.metrics_summary.get("hhi", 0),
            total_value=report.metrics_summary.get("total_value", 0),
        ),
        market_regime=_build_regime_response(report.market_regime),
        generated_at=report.generated_at.isoformat(),
    )


@router.get("/rebalancing", response_model=List[RebalancingOrderResponse])
async def get_rebalancing_suggestions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[RebalancingOrderResponse]:
    """
    Suggestions de rééquilibrage basées sur l'optimisation MPT (Markowitz).

    Retourne les ordres d'achat/vente suggérés pour maximiser le ratio de Sharpe.
    """
    report = await smart_insights_service.get_portfolio_health(
        db, str(current_user.id), days=30
    )

    return [
        RebalancingOrderResponse(
            symbol=o.symbol,
            name=o.name,
            action=o.action,
            current_weight=o.current_weight,
            target_weight=o.target_weight,
            current_value_eur=o.current_value_eur,
            target_value_eur=o.target_value_eur,
            amount_eur=o.amount_eur,
            reason=o.reason,
        ) for o in report.rebalancing_orders
    ]


@router.get("/anomalies-impact", response_model=List[AnomalyImpactResponse])
async def get_anomalies_with_impact(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AnomalyImpactResponse]:
    """
    Anomalies détectées avec calcul de l'impact en EUR.

    Retourne les mouvements anormaux sur vos positions avec leur impact financier.
    """
    report = await smart_insights_service.get_portfolio_health(
        db, str(current_user.id), days=30
    )

    return [
        AnomalyImpactResponse(
            symbol=a.symbol,
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            description=a.description,
            price_change_percent=a.price_change_percent,
            position_value_eur=a.position_value_eur,
            impact_eur=a.impact_eur,
            detected_at=a.detected_at.isoformat() if a.detected_at else "",
        ) for a in report.anomaly_impacts
    ]
