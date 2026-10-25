import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class GoalStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    REACHED = "REACHED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class GoalPriority(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class GoalType(enum.StrEnum):
    """``ASSET`` : objectif d'investissement classique ; ``SAVINGS`` : épargne de sécurité (liquidités seules)."""

    ASSET = "ASSET"
    SAVINGS = "SAVINGS"


class GoalStrategy(enum.StrEnum):
    AGGRESSIVE = "AGGRESSIVE"
    MODERATE = "MODERATE"
    CONSERVATIVE = "CONSERVATIVE"


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_type: Mapped[GoalType] = mapped_column(
        Enum(GoalType), default=GoalType.ASSET, nullable=False, server_default="ASSET"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    target_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[GoalPriority] = mapped_column(Enum(GoalPriority), default=GoalPriority.MEDIUM, nullable=False)
    strategy_type: Mapped[GoalStrategy] = mapped_column(
        Enum(GoalStrategy), default=GoalStrategy.MODERATE, nullable=False
    )
    status: Mapped[GoalStatus] = mapped_column(Enum(GoalStatus), default=GoalStatus.ACTIVE, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), default="target", nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#6366f1", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
