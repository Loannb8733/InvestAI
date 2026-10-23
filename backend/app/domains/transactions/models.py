import enum
import hashlib
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base

HASH_SCALE = 12


class TransactionType(enum.StrEnum):
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


def _canonical_decimal(value: object, scale: int) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    with localcontext() as context:
        context.prec = 50
        return format(number.quantize(Decimal(1).scaleb(-scale)), "f")


def compute_transaction_hash(
    asset_id: str, transaction_type: str, quantity: object, price: object, executed_at: object
) -> str:
    """Empreinte anti-doublon : actif, type, quantité et prix à 12 décimales, jour d'exécution.

    La plateforme et l'identifiant externe en sont exclus : la même opération
    importée par CSV puis par synchronisation donne la même empreinte.
    """
    day = str(executed_at)[:10] if executed_at else ""
    parts = [
        asset_id,
        transaction_type,
        _canonical_decimal(quantity, HASH_SCALE),
        _canonical_decimal(price, HASH_SCALE),
        day,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(precision=30, scale=12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(precision=24, scale=12), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(precision=24, scale=12), default=Decimal("0"), nullable=False)
    fee_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(precision=30, scale=12), nullable=True)
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    internal_hash: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

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
        """Recalcule et pose ``internal_hash`` depuis les champs courants."""
        day = self.executed_at.strftime("%Y-%m-%d") if self.executed_at else ""
        self.internal_hash = compute_transaction_hash(
            str(self.asset_id), self.transaction_type.value, self.quantity, self.price, day
        )
        return self.internal_hash
