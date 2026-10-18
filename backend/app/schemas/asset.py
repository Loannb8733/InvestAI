"""Asset schemas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.asset import AssetType
from app.schemas._money import Money


class AssetBase(BaseModel):
    """Base asset schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(None, max_length=200)
    asset_type: AssetType
    currency: str = Field(default="EUR", max_length=10)


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    portfolio_id: UUID
    quantity: Money = Field(default=Decimal("0"), ge=0)
    avg_buy_price: Money = Field(default=Decimal("0"), ge=0)
    exchange: str | None = Field(None, max_length=50)
    # Crowdfunding fields
    interest_rate: Money | None = Field(None, ge=0, le=100)
    maturity_date: date | None = None
    project_status: str | None = Field(None, max_length=20)
    invested_amount: Money | None = Field(None, ge=0)


class AssetUpdate(BaseModel):
    """Schema for updating an asset."""

    name: str | None = Field(None, max_length=200)
    quantity: Money | None = Field(None, ge=0)
    avg_buy_price: Money | None = Field(None, ge=0)
    exchange: str | None = Field(None, max_length=50)
    interest_rate: Money | None = Field(None, ge=0, le=100)
    maturity_date: date | None = None
    project_status: str | None = Field(None, max_length=20)
    invested_amount: Money | None = Field(None, ge=0)


class AssetResponse(AssetBase):
    """Schema for asset response."""

    id: UUID
    portfolio_id: UUID
    quantity: Money
    avg_buy_price: Money
    exchange: str | None
    interest_rate: Money | None = None
    maturity_date: date | None = None
    project_status: str | None = None
    invested_amount: Money | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetWithMetrics(AssetResponse):
    """Schema for asset with calculated metrics."""

    current_price: Money | None = None
    current_value: Money | None = None
    total_invested: Money | None = None
    gain_loss: Money | None = None
    gain_loss_percent: float | None = None
    last_price_update: datetime | None = None
