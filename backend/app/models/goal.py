"""Goal model."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    REACHED = "reached"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    target_amount = Column(Numeric(precision=18, scale=2), nullable=False)
    current_amount = Column(Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    target_date = Column(String(50), nullable=True)
    status = Column(Enum(GoalStatus), default=GoalStatus.ACTIVE, nullable=False)
    icon = Column(String(50), default="target", nullable=False)
    color = Column(String(7), default="#6366f1", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
