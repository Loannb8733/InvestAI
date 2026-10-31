import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import RATE_LIMITS, limiter
from app.core.redis_client import cache_dashboard, get_cached_dashboard
from app.domains.dashboard.charts import (
    benchmark_series,
    ensure_json_safe,
    historical_points,
    portfolio_sparklines,
    require_owned_portfolio,
)
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.overview import build_overview
from app.domains.dashboard.schemas import (
    BenchmarkSeries,
    EnhancedDashboardResponse,
    HistoricalDataPoint,
    MunitionsResponse,
    SparklineData,
)
from app.domains.identity.dependencies import CurrentUser
from app.domains.strategies.service import strategy_service

logger = logging.getLogger(__name__)

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=EnhancedDashboardResponse)
@limiter.limit("30/minute")
async def get_dashboard(
    current_user: CurrentUser,
    db: Session,
    request: Request,
    days: int = Query(30, ge=0, le=3650),
) -> EnhancedDashboardResponse:
    """Écran complet ; days=0 signifie « Tout », et une entrée de cache d'un ancien schéma vaut un cache absent."""
    user_id = str(current_user.id)
    currency = current_user.preferred_currency or "EUR"
    cached = await get_cached_dashboard(user_id, days, currency)
    if cached is not None:
        try:
            return EnhancedDashboardResponse(**cached)
        except ValidationError as exc:
            logger.warning(
                "Dashboard : entrée de cache incompatible avec le schéma (user=%s, days=%s), recalcul — %s",
                user_id,
                days,
                exc.errors()[0].get("loc") if exc.errors() else exc,
            )
    result = await build_overview(days, current_user, db)
    await cache_dashboard(user_id, days, currency, result.model_dump(mode="json"))
    return result


@router.get("/munitions", response_model=MunitionsResponse)
@limiter.limit(RATE_LIMITS["api_read"])
async def get_munitions(
    current_user: CurrentUser,
    db: Session,
    request: Request,
    monthly_dca: float = Query(300.0, ge=0, description="Monthly DCA budget (€)"),
    profile: str = Query("moderate", description="Investment profile: aggressive/moderate/conservative"),
) -> MunitionsResponse:
    """Capacité de déploiement de l'utilisateur."""
    capacity = await strategy_service.get_deployment_capacity(
        db=db, user_id=str(current_user.id), monthly_dca=monthly_dca, profile=profile
    )
    return MunitionsResponse(
        available_liquidity=capacity.available_liquidity,
        total_value=capacity.total_value,
        liquidity_pct=capacity.liquidity_pct,
        invested_pct=capacity.invested_pct,
        next_signal_symbol=capacity.next_signal_symbol,
        next_signal_action=capacity.next_signal_action,
        next_signal_amount=capacity.next_signal_amount,
        can_execute=capacity.can_execute,
        shortfall=capacity.shortfall,
        message=capacity.message,
        profile=capacity.profile,
        deploy_to_risk=capacity.deploy_to_risk,
        keep_in_reserve=capacity.keep_in_reserve,
    )


@router.get("/portfolio/{portfolio_id}")
@limiter.limit("30/minute")
async def get_portfolio_dashboard(
    current_user: CurrentUser,
    db: Session,
    request: Request,
    portfolio_id: str,
) -> Any:
    """Métriques d'un portefeuille."""
    await require_owned_portfolio(db, portfolio_id, current_user.id)
    currency = current_user.preferred_currency or "EUR"
    return ensure_json_safe(await metrics_service.get_portfolio_metrics(db, portfolio_id, currency=currency))


@router.get("/portfolio/{portfolio_id}/history")
async def get_portfolio_history(
    current_user: CurrentUser,
    db: Session,
    portfolio_id: str,
) -> dict[str, Any]:
    """Historique d'investissement d'un portefeuille, actifs soldés compris."""
    await require_owned_portfolio(db, portfolio_id, current_user.id)
    return await metrics_service.get_portfolio_history(db, portfolio_id)


@router.get("/portfolio/{portfolio_id}/sparklines", response_model=list[SparklineData])
@limiter.limit(RATE_LIMITS["api_read"])
async def get_portfolio_sparklines(
    current_user: CurrentUser,
    db: Session,
    request: Request,
    portfolio_id: str,
    days: int = Query(30, ge=7, le=90),
) -> list[SparklineData]:
    """Mini-courbes des actifs d'un portefeuille."""
    await require_owned_portfolio(db, portfolio_id, current_user.id)
    return await portfolio_sparklines(db, portfolio_id, days)


@router.get("/historical-data", response_model=list[HistoricalDataPoint])
async def get_historical_data(
    current_user: CurrentUser,
    db: Session,
    days: int = Query(30, ge=0, le=3650),
) -> list[HistoricalDataPoint]:
    """Courbe de valeur du compte ; days=0 couvre tout l'historique."""
    return await historical_points(db, current_user.id, days)


@router.get("/benchmarks", response_model=list[BenchmarkSeries])
async def get_benchmark_data(
    current_user: CurrentUser,
    db: Session,
    days: int = Query(default=90, ge=0, le=3650),
) -> list[BenchmarkSeries]:
    """Indices de référence et portefeuille en base 100, à superposer à la courbe."""
    return await benchmark_series(db, current_user.id, days)
