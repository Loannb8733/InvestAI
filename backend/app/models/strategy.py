"""Strategy models — user and AI-generated investment strategies."""

import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class StrategySource(str, enum.Enum):
    AI = "AI"
    USER = "USER"


class StrategyStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"  # AI-suggested, not yet accepted
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class ActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    source = Column(Enum(StrategySource), nullable=False, default=StrategySource.USER)
    status = Column(Enum(StrategyStatus), nullable=False, default=StrategyStatus.ACTIVE)

    # Flexible params — structure depends on strategy type
    # e.g. {"type": "DCA", "amount": 100, "frequency": "weekly", "assets": ["BTC", "ETH"]}
    # e.g. {"type": "rebalance", "target_weights": {"BTC": 50, "ETH": 30, "SOL": 20}}
    params = Column(JSON, default=dict, nullable=False)

    # AI context — regime/confidence at time of suggestion
    ai_reasoning = Column(Text, nullable=True)
    market_regime = Column(String(50), nullable=True)
    confidence = Column(Numeric(precision=5, scale=4), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StrategyAction(Base):
    __tablename__ = "strategy_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(50), nullable=False)  # e.g. "BUY", "SELL", "REBALANCE", "HOLD"
    symbol = Column(String(50), nullable=True)
    amount = Column(Numeric(precision=18, scale=8), nullable=True)
    currency = Column(String(10), default="EUR", nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(Enum(ActionStatus), nullable=False, default=ActionStatus.PENDING)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
