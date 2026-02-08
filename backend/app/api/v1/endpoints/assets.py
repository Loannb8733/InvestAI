"""Asset endpoints."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.asset import AssetCreate, AssetResponse, AssetUpdate

router = APIRouter()


@router.get("/", response_model=List[AssetResponse])
async def list_assets(
    portfolio_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AssetResponse]:
    """List all assets for the current user, optionally filtered by portfolio."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return []

    query = select(Asset).where(
        Asset.portfolio_id.in_(portfolio_ids),
    )

    if portfolio_id:
        if portfolio_id not in portfolio_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )
        query = query.where(Asset.portfolio_id == portfolio_id)

    result = await db.execute(query.order_by(Asset.symbol))
    assets = result.scalars().all()
    return assets


@router.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset_in: AssetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    """Create a new asset."""
    # Verify portfolio belongs to user
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == asset_in.portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = portfolio_result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    # Check if asset with same symbol already exists in portfolio
    existing_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id == asset_in.portfolio_id,
            Asset.symbol == asset_in.symbol.upper(),
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset with this symbol already exists in portfolio",
        )

    asset = Asset(
        portfolio_id=asset_in.portfolio_id,
        symbol=asset_in.symbol.upper(),
        name=asset_in.name,
        asset_type=asset_in.asset_type,
        quantity=asset_in.quantity,
        avg_buy_price=asset_in.avg_buy_price,
        currency=asset_in.currency,
        exchange=asset_in.exchange,
    )

    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    # Pre-cache historical data for this asset (background)
    try:
        from app.tasks.history_cache import cache_single_asset
        cache_single_asset.delay(asset.symbol, asset.asset_type.value)
    except Exception:
        pass  # Non-critical

    return asset


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    """Get a specific asset."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    return asset


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    asset_in: AssetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    """Update an asset."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    update_data = asset_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    await db.commit()
    await db.refresh(asset)

    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    delete_transactions: bool = Query(True, description="Also delete associated transactions"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an asset (cascade handles associated transactions)."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    await db.delete(asset)
    await db.commit()
