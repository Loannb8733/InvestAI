"""Portfolio schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioBase(BaseModel):
    """Base portfolio schema."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class PortfolioCreate(PortfolioBase):
    """Schema for creating a portfolio."""


class PortfolioUpdate(BaseModel):
    """Schema for updating a portfolio."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    cash_balances: dict[str, float] | None = None


class CashBalanceUpdate(BaseModel):
    """Schema for updating cash balance on an exchange."""

    exchange: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., ge=0)


class PortfolioResponse(PortfolioBase):
    """Schema for portfolio response."""

    id: UUID
    user_id: UUID
    # Nature du portefeuille, quand elle n'est pas ordinaire. L'écran s'en sert
    # pour écarter celui du crowdfunding, qui a sa propre page — il le
    # reconnaissait auparavant à son nom, ce qu'un simple renommage suffisait à
    # défaire (NEW-68).
    kind: str | None = None
    cash_balances: dict[str, float] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioWithAssets(PortfolioResponse):
    """Schema for portfolio with assets."""

    assets: list["AssetSummary"] = []
    total_value: float = 0
    total_gain_loss: float = 0
    total_gain_loss_percent: float = 0


class AssetSummary(BaseModel):
    """Brief asset summary for portfolio view."""

    id: UUID
    symbol: str
    name: str | None
    quantity: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float

    class Config:
        from_attributes = True


# Update forward reference
PortfolioWithAssets.model_rebuild()
