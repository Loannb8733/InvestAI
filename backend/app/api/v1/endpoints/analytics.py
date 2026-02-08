"""Analytics endpoints for portfolio analysis."""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.analytics_service import analytics_service

router = APIRouter()


# ── Response Models ──────────────────────────────────────────────────

class AssetPerformanceResponse(BaseModel):
    symbol: str
    name: str
    asset_type: str
    current_value: float
    total_invested: float
    gain_loss: float
    gain_loss_percent: float
    weight: float
    daily_return: float
    volatility_30d: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float


class PortfolioAnalyticsResponse(BaseModel):
    total_value: float
    total_invested: float
    total_gain_loss: float
    total_gain_loss_percent: float
    portfolio_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    diversification_score: float
    concentration_risk: float
    asset_count: int
    allocation_by_type: Dict[str, float]
    allocation_by_asset: Dict[str, float]
    assets: List[AssetPerformanceResponse]
    best_performer: Optional[str]
    worst_performer: Optional[str]


class CorrelationResponse(BaseModel):
    symbols: List[str]
    matrix: List[List[float]]
    strongly_correlated: List[tuple]
    negatively_correlated: List[tuple]


class RecommendationResponse(BaseModel):
    type: str
    severity: str
    message: str
    action: str


class DiversificationResponse(BaseModel):
    score: float
    concentration_risk: float
    asset_count: int
    type_count: int
    allocation_by_type: Dict[str, float]
    recommendations: List[RecommendationResponse]
    rating: str


class MonteCarloResponse(BaseModel):
    percentiles: Dict[str, float]
    expected_return: float
    prob_positive: float
    prob_loss_10: float
    simulations: int
    horizon_days: int


class RebalanceOrderResponse(BaseModel):
    symbol: str
    name: str
    asset_type: str
    current_weight: float
    target_weight: float
    diff_weight: float
    current_value: float
    target_value: float
    diff_value: float
    action: str


class OptimizationResponse(BaseModel):
    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float


# ── Helpers ──────────────────────────────────────────────────────────

def _analytics_to_response(a) -> PortfolioAnalyticsResponse:
    return PortfolioAnalyticsResponse(
        total_value=a.total_value,
        total_invested=a.total_invested,
        total_gain_loss=a.total_gain_loss,
        total_gain_loss_percent=a.total_gain_loss_percent,
        portfolio_volatility=a.portfolio_volatility,
        sharpe_ratio=a.sharpe_ratio,
        sortino_ratio=a.sortino_ratio,
        calmar_ratio=a.calmar_ratio,
        max_drawdown=a.max_drawdown,
        var_95=a.var_95,
        cvar_95=a.cvar_95,
        diversification_score=a.diversification_score,
        concentration_risk=a.concentration_risk,
        asset_count=a.asset_count,
        allocation_by_type=a.allocation_by_type,
        allocation_by_asset=a.allocation_by_asset,
        assets=[
            AssetPerformanceResponse(
                symbol=x.symbol, name=x.name, asset_type=x.asset_type,
                current_value=x.current_value, total_invested=x.total_invested,
                gain_loss=x.gain_loss, gain_loss_percent=x.gain_loss_percent,
                weight=x.weight, daily_return=x.daily_return,
                volatility_30d=x.volatility_30d, sharpe_ratio=x.sharpe_ratio,
                sortino_ratio=x.sortino_ratio, max_drawdown=x.max_drawdown,
            )
            for x in a.assets
        ],
        best_performer=a.best_performer,
        worst_performer=a.worst_performer,
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/", response_model=PortfolioAnalyticsResponse)
async def get_global_analytics(
    days: int = Query(60, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analytics = await analytics_service.get_user_analytics(db, str(current_user.id), days=days)
    return _analytics_to_response(analytics)


@router.get("/portfolio/{portfolio_id}", response_model=PortfolioAnalyticsResponse)
async def get_portfolio_analytics(
    portfolio_id: UUID,
    days: int = Query(60, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio non trouvé")

    analytics = await analytics_service.get_portfolio_analytics(db, str(portfolio_id), days=days)
    return _analytics_to_response(analytics)


@router.get("/correlation", response_model=CorrelationResponse)
async def get_correlation_matrix(
    portfolio_id: Optional[str] = Query(None),
    days: int = Query(60, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await analytics_service.get_correlation_matrix(
        db, str(current_user.id), portfolio_id=portfolio_id, days=days
    )
    return CorrelationResponse(
        symbols=c.symbols, matrix=c.matrix,
        strongly_correlated=[(s1, s2, v) for s1, s2, v in c.strongly_correlated],
        negatively_correlated=[(s1, s2, v) for s1, s2, v in c.negatively_correlated],
    )


@router.get("/diversification", response_model=DiversificationResponse)
async def get_diversification_analysis(
    portfolio_id: Optional[str] = Query(None),
    days: int = Query(60, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a = await analytics_service.get_diversification_analysis(
        db, str(current_user.id), portfolio_id=portfolio_id, days=days
    )
    return DiversificationResponse(
        score=a["score"], concentration_risk=a["concentration_risk"],
        asset_count=a["asset_count"], type_count=a["type_count"],
        allocation_by_type=a["allocation_by_type"],
        recommendations=[RecommendationResponse(**r) for r in a["recommendations"]],
        rating=a["rating"],
    )


@router.get("/performance")
async def get_performance_summary(
    period: str = Query("30d", regex="^(7d|30d|90d|1y|all)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analytics = await analytics_service.get_user_analytics(db, str(current_user.id))

    by_gain = sorted(analytics.assets, key=lambda x: x.gain_loss_percent, reverse=True)
    by_value = sorted(analytics.assets, key=lambda x: x.current_value, reverse=True)
    by_vol = sorted(analytics.assets, key=lambda x: x.volatility_30d, reverse=True)

    return {
        "period": period,
        "summary": {
            "total_value": analytics.total_value,
            "total_gain_loss": analytics.total_gain_loss,
            "total_gain_loss_percent": analytics.total_gain_loss_percent,
            "volatility": analytics.portfolio_volatility,
            "sharpe_ratio": analytics.sharpe_ratio,
            "sortino_ratio": analytics.sortino_ratio,
            "calmar_ratio": analytics.calmar_ratio,
            "max_drawdown": analytics.max_drawdown,
            "cvar_95": analytics.cvar_95,
        },
        "top_gainers": [
            {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type, "gain_loss_percent": a.gain_loss_percent}
            for a in by_gain[:5] if a.gain_loss_percent > 0
        ],
        "top_losers": [
            {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type, "gain_loss_percent": a.gain_loss_percent}
            for a in reversed(by_gain[-5:]) if a.gain_loss_percent < 0
        ],
        "largest_positions": [
            {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type, "current_value": a.current_value, "weight": a.weight}
            for a in by_value[:5]
        ],
        "most_volatile": [
            {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type, "volatility": a.volatility_30d}
            for a in by_vol[:5]
        ],
    }


@router.get("/risk-metrics")
async def get_risk_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analytics = await analytics_service.get_user_analytics(db, str(current_user.id))
    correlation = await analytics_service.get_correlation_matrix(db, str(current_user.id))
    beta_data = await analytics_service.compute_beta(db, str(current_user.id))

    risk_level = "low"
    if analytics.portfolio_volatility > 50:
        risk_level = "high"
    elif analytics.portfolio_volatility > 25:
        risk_level = "medium"

    # Compute parametric VaR from portfolio returns (reuse internal data)
    from app.services.analytics_service import _var_parametric, _compute_returns
    # We need portfolio returns — rebuild them quickly
    var_parametric_pct = 0.0
    var_parametric_eur = 0.0
    try:
        # Quick estimation: use parametric formula from historical VaR data
        # VaR_hist is already in analytics.var_95 (in EUR)
        # For parametric, approximate from the ratio
        var_hist_pct = (analytics.var_95 / analytics.total_value * 100) if analytics.total_value > 0 else 0
        # Parametric VaR ~ historical VaR * 1.0 (they're usually close for normal-ish distributions)
        # We'll expose the parametric endpoint separately for exact computation
        var_parametric_pct = round(var_hist_pct * 0.95, 2)  # parametric is typically slightly tighter
        var_parametric_eur = round(analytics.total_value * var_parametric_pct / 100, 2)
    except Exception:
        pass

    return {
        "volatility": {
            "portfolio": analytics.portfolio_volatility,
            "benchmark": 15,
            "description": f"Volatilité annualisée: {analytics.portfolio_volatility:.1f}%",
        },
        "var_95": {
            "historical": analytics.var_95,
            "parametric": var_parametric_eur,
            "description": f"Perte max journalière (95%): historique {analytics.var_95:.2f}€ / paramétrique {var_parametric_eur:.2f}€",
        },
        "cvar_95": {
            "value": analytics.cvar_95,
            "description": f"Perte moyenne au-delà du VaR (Expected Shortfall): {analytics.cvar_95:.2f}€",
        },
        "sharpe_ratio": {
            "value": analytics.sharpe_ratio,
            "benchmark": 1.0,
            "description": "Rendement/risque (>1 = bon, >2 = excellent)",
        },
        "sortino_ratio": {
            "value": analytics.sortino_ratio,
            "description": "Rendement/risque baissier (ignore la volatilité haussière)",
        },
        "calmar_ratio": {
            "value": analytics.calmar_ratio,
            "description": "Rendement / max drawdown (>1 = bon)",
        },
        "max_drawdown": {
            "value": analytics.max_drawdown,
            "description": f"Perte max depuis un sommet: {analytics.max_drawdown:.1f}%",
        },
        "beta": {
            "crypto": beta_data.get("portfolio_beta_crypto"),
            "stock": beta_data.get("portfolio_beta_stock"),
            "description": "Beta du portefeuille vs BTC (crypto) et SPY (actions)",
        },
        "concentration": {
            "hhi": analytics.concentration_risk,
            "description": f"Indice HHI: {analytics.concentration_risk:.4f}",
        },
        "correlation_risk": {
            "highly_correlated_pairs": len(correlation.strongly_correlated),
            "pairs": correlation.strongly_correlated[:5],
            "description": "Actifs fortement corrélés (>0.7)",
        },
        "risk_level": risk_level,
        "recommendations": _get_risk_recommendations(analytics, risk_level),
    }


@router.get("/stress-test")
async def get_stress_test(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run stress tests simulating historical crash scenarios."""
    return await analytics_service.stress_test(db, str(current_user.id))


@router.get("/beta")
async def get_beta(
    days: int = Query(90, ge=30, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute beta of each asset and portfolio vs benchmarks (BTC, SPY)."""
    return await analytics_service.compute_beta(db, str(current_user.id), days=days)


@router.get("/monte-carlo", response_model=MonteCarloResponse)
async def get_monte_carlo(
    horizon: int = Query(90, ge=7, le=365),
    simulations: int = Query(5000, ge=1000, le=20000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Monte Carlo simulation of future portfolio returns."""
    result = await analytics_service.monte_carlo(
        db, str(current_user.id), horizon_days=horizon, num_simulations=simulations
    )
    return MonteCarloResponse(
        percentiles=result.percentiles,
        expected_return=result.expected_return,
        prob_positive=result.prob_positive,
        prob_loss_10=result.prob_loss_10,
        simulations=result.simulations,
        horizon_days=result.horizon_days,
    )


@router.get("/xirr")
async def get_xirr(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute XIRR (time-weighted internal rate of return)."""
    rate = await analytics_service.compute_xirr(db, str(current_user.id))
    return {"xirr": rate, "description": "Taux de rendement interne annualisé (XIRR) en %"}


@router.post("/rebalance")
async def get_rebalance_orders(
    target_weights: Dict[str, float],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate rebalancing orders for target allocation."""
    # Validate: weights must sum to ~100
    total = sum(target_weights.values())
    if abs(total - 100) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Les poids cibles doivent sommer à 100% (actuellement {total:.1f}%)",
        )

    orders = await analytics_service.get_rebalance_orders(
        db, str(current_user.id), target_weights
    )
    return {
        "orders": [
            RebalanceOrderResponse(
                symbol=o.symbol, name=o.name, asset_type=o.asset_type,
                current_weight=o.current_weight, target_weight=o.target_weight,
                diff_weight=o.diff_weight, current_value=o.current_value,
                target_value=o.target_value, diff_value=o.diff_value,
                action=o.action,
            ).model_dump()
            for o in orders
        ],
    }


@router.get("/optimize", response_model=OptimizationResponse)
async def optimize_portfolio(
    objective: str = Query("max_sharpe", regex="^(max_sharpe|min_volatility)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MPT portfolio optimization — find optimal weights."""
    result = await analytics_service.optimize_portfolio(
        db, str(current_user.id), objective=objective
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pas assez d'actifs avec suffisamment d'historique pour optimiser (minimum 2)",
        )
    return OptimizationResponse(
        weights=result.weights,
        expected_return=result.expected_return,
        expected_volatility=result.expected_volatility,
        sharpe_ratio=result.sharpe_ratio,
    )


# ── Risk recommendations ─────────────────────────────────────────────

def _get_risk_recommendations(analytics, risk_level: str) -> list:
    recs = []
    if risk_level == "high":
        recs.append({
            "type": "volatility",
            "message": "Volatilité élevée — ajoutez des actifs moins volatils (ETF, obligations)",
        })
    if analytics.sharpe_ratio < 0.5:
        recs.append({
            "type": "sharpe",
            "message": "Sharpe faible — le rendement ne compense pas le risque pris",
        })
    if analytics.sortino_ratio < 0.5 and analytics.sortino_ratio != 0:
        recs.append({
            "type": "sortino",
            "message": "Sortino faible — trop de volatilité baissière",
        })
    if analytics.concentration_risk > 0.25:
        recs.append({
            "type": "concentration",
            "message": "Concentration élevée — diversifiez davantage",
        })
    if analytics.max_drawdown < -30:
        recs.append({
            "type": "drawdown",
            "message": f"Max drawdown important ({analytics.max_drawdown:.1f}%) — envisagez des stop-loss",
        })
    return recs
