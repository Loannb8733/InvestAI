"""Transaction model."""

import enum
import hashlib
import uuid
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, text
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

    Based on: asset_id + type + quantity (12 decimals) + price (12 decimals)
              + executed_at (DATE precision only).

    Quantity and price are hashed at the FULL column precision (Numeric scale 12)
    via Decimal, not float-formatted to 8 decimals. The old ``f"{float(x):.8f}"``
    collapsed micro-price assets to "0.00000000" (e.g. PEPE at 1e-9), so two
    distinct same-day trades hashed identically and the second was wrongly
    dropped as a duplicate.

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
        _canonical_decimal(quantity, 12),
        _canonical_decimal(price, 12),
        date_str,
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _canonical_decimal(value: object, scale: int) -> str:
    """Format a numeric value as a canonical fixed-scale decimal string.

    Uses a wide local context (prec 50) so high-supply quantities at
    Numeric(30,12) never overflow the default 28-digit precision. Invalid
    inputs degrade to "0" rather than raising.
    """
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    with localcontext() as ctx:
        ctx.prec = 50
        # format(..., "f") forces fixed-point (no scientific notation like 1.2E-9),
        # so the hashed string is stable and human-readable.
        return format(d.quantize(Decimal(1).scaleb(-scale)), "f")


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
    STAKING = "staking"
    UNSTAKING = "unstaking"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    related_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    internal_hash = Column(String(40), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_transactions_executed_at", "executed_at"),
        Index(
            "uq_transactions_internal_hash",
            "internal_hash",
            unique=True,
            postgresql_where=text("internal_hash IS NOT NULL"),
        ),
        CheckConstraint("quantity >= 0", name="ck_transactions_quantity_positive"),
        CheckConstraint("price >= 0", name="ck_transactions_price_positive"),
        CheckConstraint("fee >= 0", name="ck_transactions_fee_positive"),
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
