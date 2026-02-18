"""Calendar event model."""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class EventType(str, enum.Enum):
    DIVIDEND = "dividend"
    RENT = "rent"
    INTEREST = "interest"
    PAYMENT_DUE = "payment_due"
    REBALANCE = "rebalance"
    TAX_DEADLINE = "tax_deadline"
    REMINDER = "reminder"
    OTHER = "other"


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(Enum(EventType), nullable=False)
    event_date = Column(DateTime(timezone=True), nullable=False)
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_rule = Column(String(100), nullable=True)
    amount = Column(Numeric(precision=18, scale=2), nullable=True)
    currency = Column(String(10), default="EUR", nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
