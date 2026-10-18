"""Transaction schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.transaction import TransactionType
from app.schemas._money import Money


class TransactionBase(BaseModel):
    """Base transaction schema."""

    transaction_type: TransactionType
    quantity: Money = Field(..., gt=0)
    price: Money = Field(..., ge=0)
    fee: Money = Field(default=Decimal("0"), ge=0)
    fee_currency: str | None = Field(None, max_length=10)  # Currency/asset of the fee
    currency: str = Field(default="EUR", max_length=10)
    executed_at: datetime | None = None
    notes: str | None = None


class TransactionCreate(TransactionBase):
    """Schema for creating a transaction."""

    asset_id: UUID
    exchange: str | None = Field(None, max_length=50)
    external_id: str | None = Field(None, max_length=100)
    destination_exchange: str | None = Field(
        None,
        max_length=50,
        description="For transfer_out: destination platform (creates mirror transfer_in)",
    )


class TransactionUpdate(BaseModel):
    """Schema for updating a transaction."""

    transaction_type: TransactionType | None = None
    quantity: Money | None = Field(None, gt=0)
    price: Money | None = Field(None, ge=0)
    fee: Money | None = Field(None, ge=0)
    fee_currency: str | None = Field(None, max_length=10)
    currency: str | None = Field(None, max_length=10)
    executed_at: datetime | None = None
    exchange: str | None = Field(None, max_length=50)
    notes: str | None = None


class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: UUID
    asset_id: UUID
    transaction_type: TransactionType
    quantity: Money = Field(..., ge=0)  # Allow 0 for existing data
    price: Money = Field(..., ge=0)
    fee: Money = Field(default=Decimal("0"), ge=0)
    fee_currency: str | None = Field(None, max_length=10)
    currency: str = Field(default="EUR", max_length=10)
    executed_at: datetime | None = None
    notes: str | None = None
    exchange: str | None
    external_id: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionWithAsset(TransactionResponse):
    """Schema for transaction with asset details."""

    asset_symbol: str
    asset_name: str | None
    asset_type: str
