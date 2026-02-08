"""Transaction schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.transaction import TransactionType


class TransactionBase(BaseModel):
    """Base transaction schema."""

    transaction_type: TransactionType
    quantity: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., ge=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    fee_currency: Optional[str] = Field(None, max_length=10)  # Currency/asset of the fee
    currency: str = Field(default="EUR", max_length=10)
    executed_at: Optional[datetime] = None
    notes: Optional[str] = None


class TransactionCreate(TransactionBase):
    """Schema for creating a transaction."""

    asset_id: UUID
    exchange: Optional[str] = Field(None, max_length=50)
    external_id: Optional[str] = Field(None, max_length=100)


class TransactionUpdate(BaseModel):
    """Schema for updating a transaction."""

    transaction_type: Optional[TransactionType] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, ge=0)
    fee: Optional[Decimal] = Field(None, ge=0)
    fee_currency: Optional[str] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, max_length=10)
    executed_at: Optional[datetime] = None
    exchange: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: UUID
    asset_id: UUID
    transaction_type: TransactionType
    quantity: Decimal = Field(..., ge=0)  # Allow 0 for existing data
    price: Decimal = Field(..., ge=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    fee_currency: Optional[str] = Field(None, max_length=10)
    currency: str = Field(default="EUR", max_length=10)
    executed_at: Optional[datetime] = None
    notes: Optional[str] = None
    exchange: Optional[str]
    external_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionWithAsset(TransactionResponse):
    """Schema for transaction with asset details."""

    asset_symbol: str
    asset_name: Optional[str]
    asset_type: str
