from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.analytics.platforms import platform_distribution
from app.domains.analytics.results import AssetPerformance, PortfolioAnalytics
from app.domains.analytics.ruin_alert import send_ruin_alert
from app.domains.analytics.schemas import (
    CorrelationResponse,
    DiversificationResponse,
    MonteCarloResponse,
    OptimizationResponse,
    PerformanceSummaryResponse,
    PlatformDistributionItem,
    PortfolioAnalyticsResponse,
    RebalanceOrderResponse,
    RebalanceResponse,
    RecommendationResponse,
    XIRRResponse,
)
from app.domains.analytics.service import analytics_service
from app.domains.identity.dependencies import CurrentUser
from app.domains.insights.market_regime import current_vol_regime
from app.domains.portfolio.models import Portfolio

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
Days = Annotated[int, Query(ge=0, le=365)]
PortfolioFilter = Annotated[str | None, Query()]

ALL_HISTORY_DAYS = 3650
RUIN_ALERT_THRESHOLD = 20.0
PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": 0}


def _window(days: int) -> int:
    return ALL_HISTORY_DAYS if days == 0 else days


def _analytics_to_response(a: PortfolioAnalytics) -> PortfolioAnalyticsResponse:
    return PortfolioAnalyticsResponse.model_validate(asdict(a))


def _summary_item(a: AssetPerformance, **fields: Any) -> dict[str, Any]:
    return {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type, **fields}


def _performance_summary(period: str, analytics: PortfolioAnalytics) -> dict[str, Any]:
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
            _summary_item(a, gain_loss_percent=a.gain_loss_percent) for a in by_gain[:5] if a.gain_loss_percent > 0
        ],
        "top_losers": [
            _summary_item(a, gain_loss_percent=a.gain_loss_percent)
            for a in reversed(by_gain[-5:])
            if a.gain_loss_percent < 0
        ],
        "largest_positions": [_summary_item(a, current_value=a.current_value, weight=a.weight) for a in by_value[:5]],
        "most_volatile": [_summary_item(a, volatility=a.volatility_30d) for a in by_vol[:5]],
    }


@router.get("", response_model=PortfolioAnalyticsResponse)
async def get_global_analytics(user: CurrentUser, session: Session, days: Days = 60) -> PortfolioAnalyticsResponse:
    analytics = await analytics_service.get_user_analytics(session, str(user.id), days=_window(days))
    return _analytics_to_response(analytics)


@router.get("/portfolio/{portfolio_id}", response_model=PortfolioAnalyticsResponse)
async def get_portfolio_analytics(
    portfolio_id: UUID, user: CurrentUser, session: Session, days: Days = 60
) -> PortfolioAnalyticsResponse:
    days = _window(days)
    result = await session.execute(select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio non trouvé")

    analytics = await analytics_service.get_portfolio_analytics(session, str(portfolio_id), days=days)
    return _analytics_to_response(analytics)


@router.get("/correlation", response_model=CorrelationResponse)
async def get_correlation_matrix(
    user: CurrentUser, session: Session, portfolio_id: PortfolioFilter = None, days: Days = 60
) -> CorrelationResponse:
    c = await analytics_service.get_correlation_matrix(
        session, str(user.id), portfolio_id=portfolio_id, days=_window(days)
    )
    return CorrelationResponse(
        symbols=c.symbols,
        matrix=c.matrix,
        strongly_correlated=[(s1, s2, v) for s1, s2, v in c.strongly_correlated],
        negatively_correlated=[(s1, s2, v) for s1, s2, v in c.negatively_correlated],
    )


@router.get("/diversification", response_model=DiversificationResponse)
async def get_diversification_analysis(
    user: CurrentUser, session: Session, portfolio_id: PortfolioFilter = None, days: Days = 60
) -> DiversificationResponse:
    a = await analytics_service.get_diversification_analysis(
        session, str(user.id), portfolio_id=portfolio_id, days=_window(days)
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
    user: CurrentUser,
    session: Session,
    period: Annotated[str, Query(pattern="^(1d|7d|30d|90d|1y|all)$")] = "30d",
    portfolio_id: PortfolioFilter = None,
) -> dict[str, Any]:
    days = PERIOD_DAYS.get(period, 60)
    if portfolio_id:
        analytics = await analytics_service.get_portfolio_analytics(session, portfolio_id, days=days)
    else:
        analytics = await analytics_service.get_user_analytics(session, str(user.id), days=days)
    return _performance_summary(period, analytics)


@router.get("/stress-test", response_model=dict)
async def get_stress_test(
    user: CurrentUser,
    session: Session,
    portfolio_id: PortfolioFilter = None,
    scenario_ids: Annotated[str | None, Query(description="Comma-separated scenario IDs to filter")] = None,
) -> dict[str, Any]:
    """Scénarios de krach historiques appliqués au patrimoine, dans la devise préférée de l'utilisateur."""
    currency = getattr(user, "preferred_currency", "EUR") or "EUR"
    ids = [s.strip() for s in scenario_ids.split(",") if s.strip()] if scenario_ids else None
    return await analytics_service.stress_test(
        session, str(user.id), portfolio_id=portfolio_id, currency=currency, scenario_ids=ids
    )


@router.get("/beta", response_model=dict)
async def get_beta(
    user: CurrentUser,
    session: Session,
    days: Annotated[int, Query(ge=30, le=365)] = 90,
    portfolio_id: PortfolioFilter = None,
) -> dict[str, Any]:
    """Bêta de chaque actif et du portefeuille, contre BTC pour la crypto et SPY pour le reste."""
    return await analytics_service.compute_beta(session, str(user.id), days=days, portfolio_id=portfolio_id)


@router.get("/monte-carlo", response_model=MonteCarloResponse)
async def get_monte_carlo(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: Session,
    horizon: Annotated[int, Query(ge=7, le=365)] = 90,
    simulations: Annotated[int, Query(ge=1000, le=20000)] = 5000,
    portfolio_id: PortfolioFilter = None,
    annual_withdrawal_rate: Annotated[
        float, Query(ge=0, le=100, description="Annual withdrawal rate (%) — proportional mode")
    ] = 0.0,
    ter_percentage: Annotated[float, Query(ge=0, le=5, description="Annual TER/expense ratio (%)")] = 0.0,
    monthly_withdrawal: Annotated[
        float,
        Query(ge=0, le=1_000_000, description="Fixed monthly withdrawal (€) — absolute mode, overrides rate"),
    ] = 0.0,
) -> MonteCarloResponse:
    """Monte-Carlo au régime de volatilité courant ; au-delà de 20 % de probabilité de ruine, une alerte Telegram part
    en tâche de fond."""
    vol_regime = await current_vol_regime()
    result = await analytics_service.monte_carlo(
        session,
        str(user.id),
        horizon_days=horizon,
        num_simulations=simulations,
        portfolio_id=portfolio_id,
        annual_withdrawal_rate=annual_withdrawal_rate,
        ter_percentage=ter_percentage,
        monthly_withdrawal=monthly_withdrawal,
        vol_regime=vol_regime,
    )

    if result.prob_ruin > RUIN_ALERT_THRESHOLD and user.telegram_enabled and user.telegram_chat_id:
        background_tasks.add_task(
            send_ruin_alert,
            chat_id=user.telegram_chat_id,
            user_id=str(user.id),
            prob_ruin=result.prob_ruin,
            horizon_days=horizon,
            withdrawal_rate=annual_withdrawal_rate,
            ter=ter_percentage,
            monthly_wd=monthly_withdrawal,
        )

    return MonteCarloResponse.model_validate(asdict(result))


@router.get("/xirr", response_model=XIRRResponse)
async def get_xirr(user: CurrentUser, session: Session) -> dict[str, Any]:
    """TRI annualisé (XIRR) en %, dans la devise préférée de l'utilisateur."""
    currency = getattr(user, "preferred_currency", "EUR") or "EUR"
    rate = await analytics_service.compute_xirr(session, str(user.id), currency=currency)
    return {
        "xirr": rate,
        "currency": currency,
        "description": "Taux de rendement interne annualisé (XIRR) en %",
    }


@router.post("/rebalance", response_model=RebalanceResponse)
async def get_rebalance_orders(target_weights: dict[str, float], user: CurrentUser, session: Session) -> dict[str, Any]:
    """Ordres de rééquilibrage vers une allocation cible, dont les poids doivent sommer à 100 % (± 1)."""
    total = sum(target_weights.values())
    if abs(total - 100) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Les poids cibles doivent sommer à 100% (actuellement {total:.1f}%)",
        )

    orders = await analytics_service.get_rebalance_orders(session, str(user.id), target_weights)
    return {"orders": [RebalanceOrderResponse.model_validate(asdict(o)).model_dump() for o in orders]}


@router.get("/optimize", response_model=OptimizationResponse)
async def optimize_portfolio(
    user: CurrentUser,
    session: Session,
    objective: Annotated[str, Query(pattern="^(max_sharpe|min_volatility)$")] = "max_sharpe",
    days: Annotated[int, Query(ge=30, le=365)] = 90,
) -> OptimizationResponse:
    """Optimisation de Markowitz : pondérations au Sharpe maximal ou à la volatilité minimale."""
    result = await analytics_service.optimize_portfolio(session, str(user.id), objective=objective, days=days)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pas assez d'actifs avec suffisamment d'historique pour optimiser (minimum 2)",
        )
    return OptimizationResponse.model_validate(asdict(result))


@router.get("/distribution/platforms", response_model=list[PlatformDistributionItem])
async def get_platform_distribution(user: CurrentUser, session: Session) -> list[PlatformDistributionItem]:
    """Valeur courante des actifs par plateforme, hors crowdfunding, avec un score de confiance par plateforme."""
    return await platform_distribution(session, user.id)
