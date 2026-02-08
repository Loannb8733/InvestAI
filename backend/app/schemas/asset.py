"""Asset schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.asset import AssetType


class AssetBase(BaseModel):
    """Base asset schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = Field(None, max_length=200)
    asset_type: AssetType
    currency: str = Field(default="EUR", max_length=10)


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    portfolio_id: UUID
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    avg_buy_price: Decimal = Field(default=Decimal("0"), ge=0)
    exchange: Optional[str] = Field(None, max_length=50)


class AssetUpdate(BaseModel):
    """Schema for updating an asset."""

    name: Optional[str] = Field(None, max_length=200)
    quantity: Optional[Decimal] = Field(None, ge=0)
    avg_buy_price: Optional[Decimal] = Field(None, ge=0)
    exchange: Optional[str] = Field(None, max_length=50)


class AssetResponse(AssetBase):
    """Schema for asset response."""

    id: UUID
    portfolio_id: UUID
    quantity: Decimal
    avg_buy_price: Decimal
    exchange: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssetWithMetrics(AssetResponse):
    """Schema for asset with calculated metrics."""

    current_price: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    total_invested: Optional[Decimal] = None
    gain_loss: Optional[Decimal] = None
    gain_loss_percent: Optional[float] = None
    last_price_update: Optional[datetime] = None
