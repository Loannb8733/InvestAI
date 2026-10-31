from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.dependencies import CurrentUser
from app.domains.insights.dca_backtest import backtest_dca
from app.domains.insights.fees import fee_analysis
from app.domains.insights.health import dashboard_summary, portfolio_health
from app.domains.insights.passive_income import passive_income
from app.domains.insights.presenters import anomaly_response, health_response
from app.domains.insights.schemas import AnomalyImpactResponse, DashboardSummaryResponse, PortfolioHealthResponse
from app.domains.insights.tax_loss import tax_loss_opportunities

router = APIRouter()
smart_router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
AnalysisDays = Annotated[int, Query(ge=7, le=365, description="Période d'analyse en jours")]


@router.get("/fees", response_model=dict)
async def get_fee_analysis(current_user: CurrentUser, db: Session) -> dict[str, Any]:
    """Frais payés : par plateforme, par actif, par mois."""
    return await fee_analysis(db, str(current_user.id))


@router.get("/tax-loss-harvesting", response_model=dict)
async def get_tax_loss_harvesting(current_user: CurrentUser, db: Session) -> dict[str, Any]:
    """Positions en moins-value latente."""
    return await tax_loss_opportunities(db, str(current_user.id))


@router.get("/passive-income", response_model=dict)
async def get_passive_income(current_user: CurrentUser, db: Session, year: int | None = Query(None)) -> dict[str, Any]:
    """Revenus passifs."""
    return await passive_income(db, str(current_user.id), year=year)


@router.get("/backtest-dca", response_model=dict)
async def get_backtest_dca(
    current_user: CurrentUser,
    symbol: str = Query(..., description="Symbole de l'actif (ex: BTC, ETH)", pattern=r"^[A-Z0-9.\-]{1,20}$"),
    asset_type: str = Query("crypto", description="Type d'actif"),
    monthly_amount: float = Query(100, ge=1, le=100000, description="Montant mensuel en EUR"),
    start_year: int = Query(2020, ge=2010, description="Année de début"),
    start_month: int = Query(1, ge=1, le=12, description="Mois de début"),
) -> dict[str, Any]:
    """Investir un montant fixe chaque mois depuis une date donnée."""
    return await backtest_dca(symbol, asset_type, monthly_amount, start_year, start_month)


@smart_router.get("/health", response_model=PortfolioHealthResponse)
async def get_portfolio_health(
    current_user: CurrentUser, db: Session, days: AnalysisDays = 30
) -> PortfolioHealthResponse:
    """Note, conseils, rééquilibrage, anomalies et régime de marché."""
    return health_response(await portfolio_health(db, str(current_user.id), days))


@smart_router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    current_user: CurrentUser, db: Session, days: AnalysisDays = 30
) -> DashboardSummaryResponse:
    """Résumé du widget du tableau de bord."""
    return DashboardSummaryResponse(**await dashboard_summary(db, str(current_user.id), days))


@smart_router.get("/anomalies-impact", response_model=list[AnomalyImpactResponse])
async def get_anomalies_with_impact(current_user: CurrentUser, db: Session) -> list[AnomalyImpactResponse]:
    """Mouvements anormaux sur les positions, avec leur effet en euros."""
    report = await portfolio_health(db, str(current_user.id), days=30)
    return [anomaly_response(impact) for impact in report.anomaly_impacts]
