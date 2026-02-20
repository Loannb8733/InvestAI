"""Transaction model."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


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
    quantity = Column(Numeric(precision=24, scale=8), nullable=False)
    price = Column(Numeric(precision=18, scale=8), nullable=False)
    fee = Column(Numeric(precision=18, scale=8), default=Decimal("0"), nullable=False)
    fee_currency = Column(String(10), nullable=True)
    currency = Column(String(10), default="EUR", nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    exchange = Column(String(50), nullable=True)
    external_id = Column(String(100), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    conversion_rate = Column(Numeric(precision=18, scale=12), nullable=True)
    related_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_transactions_executed_at", "executed_at"),)
