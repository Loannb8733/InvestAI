"""Planned order model — orders flagged via Telegram or frontend for execution."""

import enum
import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class PlannedOrderStatus(str, enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class PlannedOrder(Base):
    __tablename__ = "planned_orders"
    __table_args__ = (CheckConstraint("order_eur >= 0", name="ck_planned_orders_amount_positive"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol = Column(String(20), nullable=False)
    action = Column(String(30), nullable=False)  # ACHAT FORT, DCA, VENDRE, etc.
    order_eur = Column(Numeric(precision=12, scale=2), nullable=False, default=0)
    alpha_score = Column(Float, nullable=True)
    regime = Column(String(20), nullable=True)
    prob_ruin_before = Column(Float, nullable=True)
    prob_ruin_after = Column(Float, nullable=True)
    source = Column(String(20), nullable=False, default="telegram")  # telegram | frontend
    status = Column(
        Enum(PlannedOrderStatus),
        nullable=False,
        default=PlannedOrderStatus.PENDING,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
