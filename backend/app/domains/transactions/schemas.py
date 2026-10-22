from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.transactions.models import TransactionType
from app.schemas._money import Money


class TransactionCreate(BaseModel):
    asset_id: UUID
    transaction_type: TransactionType
    quantity: Money = Field(..., gt=0)
    price: Money = Field(..., ge=0)
    fee: Money = Field(default=Decimal("0"), ge=0)
    fee_currency: str | None = Field(None, max_length=10)
    currency: str = Field(default="EUR", max_length=10)
    executed_at: datetime | None = None
    notes: str | None = None
    exchange: str | None = Field(None, max_length=50)
    external_id: str | None = Field(None, max_length=100)
    destination_exchange: str | None = Field(
        None, max_length=50, description="Pour un transfert sortant : plateforme de destination, qui reçoit un miroir"
    )


class TransactionUpdate(BaseModel):
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
    id: UUID
    asset_id: UUID
    transaction_type: TransactionType
    quantity: Money
    price: Money
    fee: Money = Decimal("0")
    fee_currency: str | None = None
    currency: str = "EUR"
    executed_at: datetime | None = None
    notes: str | None = None
    exchange: str | None
    external_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionWithAsset(TransactionResponse):
    asset_symbol: str
    asset_name: str | None
    asset_type: str


class TransactionListPage(BaseModel):
    items: list[TransactionWithAsset]
    total: int


class DeleteAllResult(BaseModel):
    deleted_count: int


class PlatformsResponse(BaseModel):
    platforms: list[str]


class CsvImportResult(BaseModel):
    """Lignes enregistrées, en erreur, et déjà présentes (troisième issue possible d'un import)."""

    success_count: int
    error_count: int
    skipped_count: int = 0
    errors: list[str]
    created_transactions: list[UUID]


class BalanceGap(BaseModel):
    asset_id: str
    symbol: str
    exchange: str
    stored: float
    computed: float
    missing_qty: float
    missing_eur: float
    suggested_action: Literal["credit_airdrop"] = "credit_airdrop"
    source_hint: Literal["earn_pending", "airdrop", "unknown"]


class BalanceGapsResponse(BaseModel):
    count: int
    threshold_eur: float
    gaps: list[BalanceGap]


class CreditedGap(BaseModel):
    symbol: str
    exchange: str
    missing_qty: float
    missing_eur: float
    source_hint: str


class SkippedGap(BaseModel):
    symbol: str
    exchange: str
    reason: Literal["already_credited_today", "no_market_price"]


class CreditDetails(BaseModel):
    credited: list[CreditedGap] = []
    skipped: list[SkippedGap] = []


class CreditResult(BaseModel):
    credited: int
    skipped: int
    details: CreditDetails
