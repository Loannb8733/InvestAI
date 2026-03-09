"""Transaction model."""

import enum
import hashlib
import uuid
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


def compute_transaction_hash(
    asset_id: str,
    transaction_type: str,
    quantity: str,
    price: str,
    executed_at: str,
    exchange: str = "",
    external_id: str = "",
) -> str:
    """Compute a deterministic hash for transaction deduplication.

    Based on: asset_id + type + quantity (8 decimals) + price (8 decimals)
              + executed_at (DATE precision only).

    Intentionally excludes exchange and external_id so the same real-world
    transaction imported from different sources (CSV vs exchange sync)
    produces the same hash.  Date-only precision handles slight timestamp
    differences between sources.
    """
    # Normalise executed_at to DATE only (YYYY-MM-DD)
    date_str = ""
    if executed_at:
        date_str = str(executed_at)[:10]  # "2026-03-02 23:21:00" → "2026-03-02"

    parts = [
        str(asset_id),
        str(transaction_type),
        f"{float(quantity):.8f}",
        f"{float(price):.8f}",
        date_str,
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


class TransactionType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    STAKING_REWARD = "staking_reward"
    AIRDROP = "airdrop"
    CONVERSION_IN = "conversion_in"
    CONVERSION_OUT = "conversion_out"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    quantity = Column(Numeric(precision=30, scale=12), nullable=False)
    price = Column(Numeric(precision=24, scale=12), nullable=False)
    fee = Column(Numeric(precision=24, scale=12), default=Decimal("0"), nullable=False)
    fee_currency = Column(String(10), nullable=True)
    currency = Column(String(10), default="EUR", nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    exchange = Column(String(50), nullable=True)
    external_id = Column(String(100), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    conversion_rate = Column(Numeric(precision=30, scale=12), nullable=True)
    related_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True)
    internal_hash = Column(String(40), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_transactions_executed_at", "executed_at"),
        Index(
            "uq_transactions_internal_hash",
            "internal_hash",
            unique=True,
            postgresql_where=Text("internal_hash IS NOT NULL"),
        ),
    )

    def compute_hash(self) -> str:
        """Compute and set the internal_hash from current fields."""
        ts = ""
        if self.executed_at:
            ts = (
                self.executed_at.strftime("%Y-%m-%d")
                if hasattr(self.executed_at, "strftime")
                else str(self.executed_at)[:10]
            )
        h = compute_transaction_hash(
            asset_id=str(self.asset_id),
            transaction_type=self.transaction_type.value
            if hasattr(self.transaction_type, "value")
            else str(self.transaction_type),
            quantity=str(self.quantity),
            price=str(self.price),
            executed_at=ts,
        )
        self.internal_hash = h
        return h
