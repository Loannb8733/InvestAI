from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.portfolio.models import AssetType
from app.schemas._money import Money


class PortfolioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class CashBalanceUpdate(BaseModel):
    exchange: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., ge=0)


class PortfolioResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    kind: str | None = None
    cash_balances: dict[str, float] = {}
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetCreate(BaseModel):
    portfolio_id: UUID
    symbol: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(None, max_length=200)
    asset_type: AssetType
    currency: str = Field(default="EUR", max_length=10)
    quantity: Money = Field(default=Decimal("0"), ge=0)
    avg_buy_price: Money = Field(default=Decimal("0"), ge=0)
    exchange: str | None = Field(None, max_length=50)
    interest_rate: Money | None = Field(None, ge=0, le=100)
    maturity_date: date | None = None
    project_status: str | None = Field(None, max_length=20)
    invested_amount: Money | None = Field(None, ge=0)


class AssetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    quantity: Money | None = Field(None, ge=0)
    avg_buy_price: Money | None = Field(None, ge=0)
    exchange: str | None = Field(None, max_length=50)
    interest_rate: Money | None = Field(None, ge=0, le=100)
    maturity_date: date | None = None
    project_status: str | None = Field(None, max_length=20)
    invested_amount: Money | None = Field(None, ge=0)


class AssetResponse(BaseModel):
    id: UUID
    portfolio_id: UUID
    symbol: str
    name: str | None = None
    asset_type: AssetType
    currency: str
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
