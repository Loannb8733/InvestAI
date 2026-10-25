import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class StrategySource(enum.StrEnum):
    AI = "AI"
    USER = "USER"


class StrategyStatus(enum.StrEnum):
    """``PROPOSED`` : suggérée par l'IA, pas encore acceptée."""

    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class ActionStatus(enum.StrEnum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class Strategy(Base):
    """Stratégie saisie par l'utilisateur ou proposée par l'IA.

    ``params`` dépend du type, par exemple ``{"type": "DCA", "amount": 100, "frequency": "weekly",
    "assets": ["BTC", "ETH"]}`` ou ``{"type": "rebalance", "target_weights": {"BTC": 50, "ETH": 30}}`` ;
    ``ai_reasoning``, ``market_regime`` et ``confidence`` figent le contexte IA au moment de la suggestion.
    """

    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[StrategySource] = mapped_column(Enum(StrategySource), nullable=False, default=StrategySource.USER)
    status: Mapped[StrategyStatus] = mapped_column(Enum(StrategyStatus), nullable=False, default=StrategyStatus.ACTIVE)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(precision=5, scale=4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class StrategyAction(Base):
    """Action d'une stratégie ; ``action`` est un libellé libre (``BUY``, ``SELL``, ``REBALANCE``, ``HOLD``…)."""

    __tablename__ = "strategy_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=8), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), nullable=False, default=ActionStatus.PENDING)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
