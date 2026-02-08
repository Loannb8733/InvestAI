"""Insights endpoints: fee analysis, tax-loss harvesting, passive income, DCA backtest."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.insights_service import insights_service

router = APIRouter()


@router.get("/fees")
async def get_fee_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyse complète des frais : par exchange, par actif, par mois."""
    return await insights_service.get_fee_analysis(db, str(current_user.id))


@router.get("/tax-loss-harvesting")
async def get_tax_loss_harvesting(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Identifier les positions en moins-value pour optimisation fiscale."""
    return await insights_service.get_tax_loss_harvesting(db, str(current_user.id))


@router.get("/passive-income")
async def get_passive_income(
    year: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revenus passifs : dividendes, staking, intérêts, airdrops."""
    return await insights_service.get_passive_income(db, str(current_user.id), year=year)


@router.get("/backtest-dca")
async def backtest_dca(
    symbol: str = Query(..., description="Symbole de l'actif (ex: BTC, ETH)"),
    asset_type: str = Query("crypto", description="Type d'actif"),
    monthly_amount: float = Query(100, ge=1, le=100000, description="Montant mensuel en EUR"),
    start_year: int = Query(2020, ge=2010, description="Année de début"),
    start_month: int = Query(1, ge=1, le=12, description="Mois de début"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backtester une stratégie DCA : investir X€/mois depuis une date donnée."""
    return await insights_service.backtest_dca(
        symbol=symbol.upper(),
        asset_type=asset_type,
        monthly_amount=monthly_amount,
        start_year=start_year,
        start_month=start_month,
    )
