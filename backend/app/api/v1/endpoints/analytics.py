"""Analytics endpoints for portfolio analysis."""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.dependencies import get_current_user
from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.services.analytics_service import analytics_service
from app.services.smart_insights_service import smart_insights_service

logger = logging.getLogger(__name__)

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
    var_95_description: str = ""
    diversification_score: float
    concentration_risk: float
    asset_count: int
    allocation_by_type: dict[str, float]
    allocation_by_asset: dict[str, float]
    assets: list[AssetPerformanceResponse]
    best_performer: str | None
    worst_performer: str | None
    interpretations: dict[str, str] = {}


class CorrelationResponse(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]
    strongly_correlated: list[tuple]
    negatively_correlated: list[tuple]


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
    allocation_by_type: dict[str, float]
    recommendations: list[RecommendationResponse]
    rating: str


class MonteCarloResponse(BaseModel):
    percentiles: dict[str, float]
    expected_return: float
    prob_positive: float
    prob_loss_10: float
    prob_ruin: float
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
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float


class PerformanceSummaryItem(BaseModel):
    symbol: str
    name: str
    asset_type: str
    gain_loss_percent: float | None = None
    current_value: float | None = None
    weight: float | None = None
    volatility: float | None = None


class PerformanceSummaryMetrics(BaseModel):
    total_value: float
    total_gain_loss: float
    total_gain_loss_percent: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    cvar_95: float


class PerformanceSummaryResponse(BaseModel):
    period: str
    summary: PerformanceSummaryMetrics
    top_gainers: list[PerformanceSummaryItem]
    top_losers: list[PerformanceSummaryItem]
    largest_positions: list[PerformanceSummaryItem]
    most_volatile: list[PerformanceSummaryItem]


class RebalanceResponse(BaseModel):
    orders: list[dict]


class XIRRResponse(BaseModel):
    xirr: float | None
    currency: str = "EUR"
    description: str


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
        var_95_description=getattr(a, "var_95_description", ""),
        diversification_score=a.diversification_score,
        concentration_risk=a.concentration_risk,
        asset_count=a.asset_count,
        allocation_by_type=a.allocation_by_type,
        allocation_by_asset=a.allocation_by_asset,
        assets=[
            AssetPerformanceResponse(
                symbol=x.symbol,
                name=x.name,
                asset_type=x.asset_type,
                current_value=x.current_value,
                total_invested=x.total_invested,
                gain_loss=x.gain_loss,
                gain_loss_percent=x.gain_loss_percent,
                weight=x.weight,
                daily_return=x.daily_return,
                volatility_30d=x.volatility_30d,
                sharpe_ratio=x.sharpe_ratio,
                sortino_ratio=x.sortino_ratio,
                max_drawdown=x.max_drawdown,
            )
            for x in a.assets
        ],
        best_performer=a.best_performer,
        worst_performer=a.worst_performer,
        interpretations=getattr(a, "interpretations", {}),
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("", response_model=PortfolioAnalyticsResponse)
async def get_global_analytics(
    days: int = Query(60, ge=0, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if days == 0:
        days = 3650
    analytics = await analytics_service.get_user_analytics(db, str(current_user.id), days=days)
    return _analytics_to_response(analytics)


@router.get("/portfolio/{portfolio_id}", response_model=PortfolioAnalyticsResponse)
async def get_portfolio_analytics(
    portfolio_id: UUID,
    days: int = Query(60, ge=0, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if days == 0:
        days = 3650
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
    portfolio_id: str | None = Query(None),
    days: int = Query(60, ge=0, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if days == 0:
        days = 3650
    c = await analytics_service.get_correlation_matrix(db, str(current_user.id), portfolio_id=portfolio_id, days=days)
    return CorrelationResponse(
        symbols=c.symbols,
        matrix=c.matrix,
        strongly_correlated=[(s1, s2, v) for s1, s2, v in c.strongly_correlated],
        negatively_correlated=[(s1, s2, v) for s1, s2, v in c.negatively_correlated],
    )


@router.get("/diversification", response_model=DiversificationResponse)
async def get_diversification_analysis(
    portfolio_id: str | None = Query(None),
    days: int = Query(60, ge=0, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if days == 0:
        days = 3650
    a = await analytics_service.get_diversification_analysis(
        db, str(current_user.id), portfolio_id=portfolio_id, days=days
    )
    return DiversificationResponse(
        score=a["score"],
        concentration_risk=a["concentration_risk"],
        asset_count=a["asset_count"],
        type_count=a["type_count"],
        allocation_by_type=a["allocation_by_type"],
        recommendations=[RecommendationResponse(**r) for r in a["recommendations"]],
        rating=a["rating"],
    )


@router.get("/performance", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    period: str = Query("30d", pattern="^(1d|7d|30d|90d|1y|all)$"),
    portfolio_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    period_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": 0}
    days = period_map.get(period, 60)

    if portfolio_id:
        analytics = await analytics_service.get_portfolio_analytics(db, portfolio_id, days=days)
    else:
        analytics = await analytics_service.get_user_analytics(db, str(current_user.id), days=days)

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
            {
                "symbol": a.symbol,
                "name": a.name,
                "asset_type": a.asset_type,
                "gain_loss_percent": a.gain_loss_percent,
            }
            for a in by_gain[:5]
            if a.gain_loss_percent > 0
        ],
        "top_losers": [
            {
                "symbol": a.symbol,
                "name": a.name,
                "asset_type": a.asset_type,
                "gain_loss_percent": a.gain_loss_percent,
            }
            for a in reversed(by_gain[-5:])
            if a.gain_loss_percent < 0
        ],
        "largest_positions": [
            {
                "symbol": a.symbol,
                "name": a.name,
                "asset_type": a.asset_type,
                "current_value": a.current_value,
                "weight": a.weight,
            }
            for a in by_value[:5]
        ],
        "most_volatile": [
            {
                "symbol": a.symbol,
                "name": a.name,
                "asset_type": a.asset_type,
                "volatility": a.volatility_30d,
            }
            for a in by_vol[:5]
        ],
    }


@router.get("/stress-test", response_model=dict)
async def get_stress_test(
    portfolio_id: str | None = Query(None),
    scenario_ids: str | None = Query(None, description="Comma-separated scenario IDs to filter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Run stress tests simulating historical crash scenarios."""
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    ids = [s.strip() for s in scenario_ids.split(",") if s.strip()] if scenario_ids else None
    return await analytics_service.stress_test(
        db,
        str(current_user.id),
        portfolio_id=portfolio_id,
        currency=currency,
        scenario_ids=ids,
    )


@router.get("/beta", response_model=dict)
async def get_beta(
    days: int = Query(90, ge=30, le=365),
    portfolio_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Compute beta of each asset and portfolio vs benchmarks (BTC, SPY)."""
    return await analytics_service.compute_beta(db, str(current_user.id), days=days, portfolio_id=portfolio_id)


@router.get("/monte-carlo", response_model=MonteCarloResponse)
async def get_monte_carlo(
    background_tasks: BackgroundTasks,
    horizon: int = Query(90, ge=7, le=365),
    simulations: int = Query(5000, ge=1000, le=20000),
    portfolio_id: str | None = Query(None),
    annual_withdrawal_rate: float = Query(
        0.0, ge=0, le=100, description="Annual withdrawal rate (%) — proportional mode"
    ),
    ter_percentage: float = Query(0.0, ge=0, le=5, description="Annual TER/expense ratio (%)"),
    monthly_withdrawal: float = Query(
        0.0,
        ge=0,
        le=1_000_000,
        description="Fixed monthly withdrawal (€) — absolute mode, overrides rate",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Monte Carlo simulation of future portfolio returns with optional withdrawals and fees."""
    # Derive vol_regime from current market regime for regime-aware volatility
    vol_regime = await smart_insights_service.get_current_vol_regime(db, str(current_user.id))

    result = await analytics_service.monte_carlo(
        db,
        str(current_user.id),
        horizon_days=horizon,
        num_simulations=simulations,
        portfolio_id=portfolio_id,
        annual_withdrawal_rate=annual_withdrawal_rate,
        ter_percentage=ter_percentage,
        monthly_withdrawal=monthly_withdrawal,
        vol_regime=vol_regime,
    )

    # Alert user via Telegram if ruin probability exceeds 20%
    if result.prob_ruin > 20.0 and current_user.telegram_enabled and current_user.telegram_chat_id:
        background_tasks.add_task(
            _send_ruin_alert,
            chat_id=current_user.telegram_chat_id,
            user_id=str(current_user.id),
            prob_ruin=result.prob_ruin,
            horizon_days=horizon,
            withdrawal_rate=annual_withdrawal_rate,
            ter=ter_percentage,
            monthly_wd=monthly_withdrawal,
        )

    return MonteCarloResponse(
        percentiles=result.percentiles,
        expected_return=result.expected_return,
        prob_positive=result.prob_positive,
        prob_loss_10=result.prob_loss_10,
        prob_ruin=result.prob_ruin,
        simulations=result.simulations,
        horizon_days=result.horizon_days,
    )


async def _send_ruin_alert(
    chat_id: str,
    user_id: str,
    prob_ruin: float,
    horizon_days: int,
    withdrawal_rate: float,
    ter: float,
    monthly_wd: float = 0.0,
) -> None:
    """Send Telegram alert when ruin probability is dangerously high."""
    try:
        from app.services.telegram_service import telegram_service

        params_parts = []
        if monthly_wd > 0:
            params_parts.append(f"retrait {monthly_wd:.0f}€/mois")
        elif withdrawal_rate > 0:
            params_parts.append(f"retrait {withdrawal_rate:.1f}%/an")
        if ter > 0:
            params_parts.append(f"TER {ter:.2f}%")
        params_str = " + ".join(params_parts) if params_parts else "sans retraits"

        message = (
            f"📉 <b>Alerte Probabilité de Ruine</b>\n\n"
            f"Votre simulation Monte Carlo ({horizon_days}j, {params_str}) "
            f"indique une probabilité de ruine de <b>{prob_ruin:.1f}%</b>.\n\n"
            f"💡 Envisagez de réduire votre taux de retrait ou de diversifier votre portefeuille."
        )

        await telegram_service.send_smart_alert(
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            priority="critical",
            symbol="PORTFOLIO",
            alert_type="RUIN_PROBABILITY",
        )
    except Exception as exc:
        logger.warning("Ruin alert Telegram failed: %s", exc)


@router.get("/xirr", response_model=XIRRResponse)
async def get_xirr(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Compute XIRR (time-weighted internal rate of return)."""
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    rate = await analytics_service.compute_xirr(db, str(current_user.id), currency=currency)
    return {
        "xirr": rate,
        "currency": currency,
        "description": "Taux de rendement interne annualisé (XIRR) en %",
    }


@router.post("/rebalance", response_model=RebalanceResponse)
async def get_rebalance_orders(
    target_weights: dict[str, float],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Calculate rebalancing orders for target allocation."""
    # Validate: weights must sum to ~100
    total = sum(target_weights.values())
    if abs(total - 100) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Les poids cibles doivent sommer à 100% (actuellement {total:.1f}%)",
        )

    orders = await analytics_service.get_rebalance_orders(db, str(current_user.id), target_weights)
    return {
        "orders": [
            RebalanceOrderResponse(
                symbol=o.symbol,
                name=o.name,
                asset_type=o.asset_type,
                current_weight=o.current_weight,
                target_weight=o.target_weight,
                diff_weight=o.diff_weight,
                current_value=o.current_value,
                target_value=o.target_value,
                diff_value=o.diff_value,
                action=o.action,
            ).model_dump()
            for o in orders
        ],
    }


@router.get("/optimize", response_model=OptimizationResponse)
async def optimize_portfolio(
    objective: str = Query("max_sharpe", pattern="^(max_sharpe|min_volatility)$"),
    days: int = Query(90, ge=30, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """MPT portfolio optimization — find optimal weights."""
    result = await analytics_service.optimize_portfolio(db, str(current_user.id), objective=objective, days=days)
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


# ── Platform distribution ────────────────────────────────────────────


PLATFORM_TRUST_SCORES: dict[str, int] = {
    "tangem": 10,
    "ledger": 10,
    "trezor": 10,
    "safepal": 9,
    "metamask": 8,
    "binance": 7,
    "kraken": 8,
    "coinbase": 7,
    "crypto.com": 6,
    "bitstamp": 7,
    "kucoin": 5,
    "bybit": 5,
    "okx": 6,
    "gate.io": 5,
    "bitpanda": 6,
    "revolut": 6,
    "trade republic": 6,
    "tokimo": 4,
}
DEFAULT_TRUST_SCORE = 4


class PlatformDistributionItem(BaseModel):
    name: str
    value: float
    percentage: float
    trust_score: int


@router.get("/distribution/platforms", response_model=list[PlatformDistributionItem])
async def get_platform_distribution(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Aggregate current asset values grouped by exchange/platform."""
    from sqlalchemy import func as sqlfunc

    result = await db.execute(
        select(
            Asset.exchange,
            sqlfunc.sum(Asset.current_price * Asset.quantity).label("total_value"),
        )
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(
            Portfolio.user_id == current_user.id,
            Asset.quantity > 0,
            Asset.asset_type != AssetType.CROWDFUNDING,
        )
        .group_by(Asset.exchange)
    )
    rows = result.all()

    # Deduplicate case-insensitively, keep first-seen casing
    seen_names: dict[str, str] = {}
    merged: dict[str, float] = {}
    for exchange, value in rows:
        display = (exchange or "").strip() or "Non assigné"
        key = display.lower()
        if key not in seen_names:
            seen_names[key] = display
        merged[key] = merged.get(key, 0) + float(value or 0)

    grand_total = sum(merged.values())
    items = [
        PlatformDistributionItem(
            name=seen_names[key],
            value=round(val, 2),
            percentage=round(val / grand_total * 100, 1) if grand_total > 0 else 0,
            trust_score=PLATFORM_TRUST_SCORES.get(key, DEFAULT_TRUST_SCORE),
        )
        for key, val in sorted(merged.items(), key=lambda x: -x[1])
    ]
    return items


# ── Risk recommendations ─────────────────────────────────────────────
