"""Cold wallet address → label mapping endpoints.

Lets the user name their cold-wallet destination addresses so the scheduled
exchange sync routes each withdrawal to the right wallet (Tangem, Ledger, …).
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.cold_wallet_address import ColdWalletAddress
from app.models.user import User

router = APIRouter()


class ColdWalletCreate(BaseModel):
    """Create / update a cold-wallet address mapping (upsert by address)."""

    address: str = Field(..., min_length=4, max_length=255)
    label: str = Field(..., min_length=1, max_length=50)


class ColdWalletResponse(BaseModel):
    id: UUID
    address: str
    label: str
    created_at: datetime


@router.get("", response_model=list[ColdWalletResponse])
async def list_cold_wallets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ColdWalletResponse]:
    """List the current user's cold-wallet address mappings."""
    result = await db.execute(
        select(ColdWalletAddress)
        .where(ColdWalletAddress.user_id == current_user.id)
        .order_by(ColdWalletAddress.created_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=ColdWalletResponse, status_code=status.HTTP_201_CREATED)
async def upsert_cold_wallet(
    payload: ColdWalletCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ColdWalletResponse:
    """Create or rename a cold-wallet address mapping (unique per user+address)."""
    address = payload.address.strip()
    label = payload.label.strip()
    if not address or not label:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="address and label are required")

    result = await db.execute(
        select(ColdWalletAddress).where(
            ColdWalletAddress.user_id == current_user.id,
            ColdWalletAddress.address == address,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = ColdWalletAddress(user_id=current_user.id, address=address, label=label)
        db.add(entry)
    else:
        entry.label = label
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cold_wallet(
    wallet_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a cold-wallet address mapping owned by the current user."""
    result = await db.execute(
        select(ColdWalletAddress).where(
            ColdWalletAddress.id == wallet_id,
            ColdWalletAddress.user_id == current_user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cold wallet mapping not found")
    await db.delete(entry)
    await db.commit()
