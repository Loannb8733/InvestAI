"""Portfolio schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioBase(BaseModel):
    """Base portfolio schema."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class PortfolioCreate(PortfolioBase):
    """Schema for creating a portfolio."""

    pass


class PortfolioUpdate(BaseModel):
    """Schema for updating a portfolio."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    cash_balances: Optional[dict[str, float]] = None


class CashBalanceUpdate(BaseModel):
    """Schema for updating cash balance on an exchange."""

    exchange: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., ge=0)


class PortfolioResponse(PortfolioBase):
    """Schema for portfolio response."""

    id: UUID
    user_id: UUID
    cash_balances: dict[str, float] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioWithAssets(PortfolioResponse):
    """Schema for portfolio with assets."""

    assets: List["AssetSummary"] = []
    total_value: float = 0
    total_gain_loss: float = 0
    total_gain_loss_percent: float = 0


class AssetSummary(BaseModel):
    """Brief asset summary for portfolio view."""

    id: UUID
    symbol: str
    name: Optional[str]
    quantity: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float

    class Config:
        from_attributes = True


# Update forward reference
PortfolioWithAssets.model_rebuild()
