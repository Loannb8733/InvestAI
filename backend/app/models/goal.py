"""Goal model."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class GoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REACHED = "REACHED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class GoalPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class GoalType(str, enum.Enum):
    ASSET = "ASSET"  # Standard investment goal (risky assets)
    SAVINGS = "SAVINGS"  # Épargne de Sécurité (cash/stables/gold only)


class GoalStrategy(str, enum.Enum):
    AGGRESSIVE = "AGGRESSIVE"
    MODERATE = "MODERATE"
    CONSERVATIVE = "CONSERVATIVE"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_type = Column(Enum(GoalType), default=GoalType.ASSET, nullable=False, server_default="ASSET")
    name = Column(String(200), nullable=False)
    target_amount = Column(Numeric(precision=18, scale=2), nullable=False)
    current_amount = Column(Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    target_date = Column(String(50), nullable=True)
    deadline_date = Column(Date, nullable=True)
    priority = Column(Enum(GoalPriority), default=GoalPriority.MEDIUM, nullable=False)
    strategy_type = Column(Enum(GoalStrategy), default=GoalStrategy.MODERATE, nullable=False)
    status = Column(Enum(GoalStatus), default=GoalStatus.ACTIVE, nullable=False)
    icon = Column(String(50), default="target", nullable=False)
    color = Column(String(7), default="#6366f1", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
