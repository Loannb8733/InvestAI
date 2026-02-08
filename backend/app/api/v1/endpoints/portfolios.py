"""Portfolio endpoints."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse, PortfolioUpdate, CashBalanceUpdate

router = APIRouter()


@router.get("/", response_model=List[PortfolioResponse])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[PortfolioResponse]:
    """List all portfolios for the current user."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at.desc())
    )
    portfolios = result.scalars().all()
    return portfolios


@router.post("/", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    portfolio_in: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Create a new portfolio."""
    portfolio = Portfolio(
        user_id=current_user.id,
        name=portfolio_in.name,
        description=portfolio_in.description,
    )

    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)

    return portfolio


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Get a specific portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    return portfolio


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: UUID,
    portfolio_in: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Update a portfolio."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    update_data = portfolio_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(portfolio, field, value)

    await db.commit()
    await db.refresh(portfolio)

    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: UUID,
    delete_assets: bool = Query(True, description="Also delete associated assets and transactions"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a portfolio and optionally its associated assets and transactions."""
    from app.models.asset import Asset
    from app.models.transaction import Transaction

    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    if delete_assets:
        # Get all assets in this portfolio
        assets_result = await db.execute(
            select(Asset).where(Asset.portfolio_id == portfolio_id)
        )
        assets = assets_result.scalars().all()

        # Delete all transactions for each asset
        for asset in assets:
            trans_result = await db.execute(
                select(Transaction).where(Transaction.asset_id == asset.id)
            )
            transactions = trans_result.scalars().all()
            for transaction in transactions:
                await db.delete(transaction)
            await db.delete(asset)

    # Hard delete the portfolio
    await db.delete(portfolio)
    await db.commit()


@router.put("/{portfolio_id}/cash-balance", response_model=PortfolioResponse)
async def update_cash_balance(
    portfolio_id: UUID,
    cash_update: CashBalanceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Update cash balance for a specific exchange."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    # Update or remove cash balance for the exchange
    cash_balances = dict(portfolio.cash_balances or {})
    if cash_update.amount > 0:
        cash_balances[cash_update.exchange] = cash_update.amount
    else:
        cash_balances.pop(cash_update.exchange, None)

    portfolio.cash_balances = cash_balances
    await db.commit()
    await db.refresh(portfolio)

    return portfolio


@router.delete("/{portfolio_id}/cash-balance/{exchange}", response_model=PortfolioResponse)
async def delete_cash_balance(
    portfolio_id: UUID,
    exchange: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Remove cash balance for a specific exchange."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    cash_balances = dict(portfolio.cash_balances or {})
    cash_balances.pop(exchange, None)
    portfolio.cash_balances = cash_balances

    await db.commit()
    await db.refresh(portfolio)

    return portfolio
