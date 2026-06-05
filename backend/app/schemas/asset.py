"""Asset schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.asset import AssetType
from app.schemas._money import Money


class AssetBase(BaseModel):
    """Base asset schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = Field(None, max_length=200)
    asset_type: AssetType
    currency: str = Field(default="EUR", max_length=10)


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    portfolio_id: UUID
    quantity: Money = Field(default=Decimal("0"), ge=0)
    avg_buy_price: Money = Field(default=Decimal("0"), ge=0)
    exchange: Optional[str] = Field(None, max_length=50)
    # Crowdfunding fields
    interest_rate: Optional[Money] = Field(None, ge=0, le=100)
    maturity_date: Optional[date] = None
    project_status: Optional[str] = Field(None, max_length=20)
    invested_amount: Optional[Money] = Field(None, ge=0)


class AssetUpdate(BaseModel):
    """Schema for updating an asset."""

    name: Optional[str] = Field(None, max_length=200)
    quantity: Optional[Money] = Field(None, ge=0)
    avg_buy_price: Optional[Money] = Field(None, ge=0)
    exchange: Optional[str] = Field(None, max_length=50)
    interest_rate: Optional[Money] = Field(None, ge=0, le=100)
    maturity_date: Optional[date] = None
    project_status: Optional[str] = Field(None, max_length=20)
    invested_amount: Optional[Money] = Field(None, ge=0)


class AssetResponse(AssetBase):
    """Schema for asset response."""

    id: UUID
    portfolio_id: UUID
    quantity: Money
    avg_buy_price: Money
    exchange: Optional[str]
    interest_rate: Optional[Money] = None
    maturity_date: Optional[date] = None
    project_status: Optional[str] = None
    invested_amount: Optional[Money] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssetWithMetrics(AssetResponse):
    """Schema for asset with calculated metrics."""

    current_price: Optional[Money] = None
    current_value: Optional[Money] = None
    total_invested: Optional[Money] = None
    gain_loss: Optional[Money] = None
    gain_loss_percent: Optional[float] = None
    last_price_update: Optional[datetime] = None
