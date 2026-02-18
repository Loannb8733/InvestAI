"""Alert model."""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class AlertCondition(str, enum.Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    CHANGE_PERCENT_UP = "change_percent_up"
    CHANGE_PERCENT_DOWN = "change_percent_down"
    DAILY_CHANGE_UP = "daily_change_up"
    DAILY_CHANGE_DOWN = "daily_change_down"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    condition = Column(Enum(AlertCondition), nullable=False)
    threshold = Column(Numeric(precision=18, scale=8), nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    triggered_at = Column(String(255), nullable=True)
    triggered_count = Column(Integer, default=0, nullable=False)
    notify_email = Column(Boolean, default=True, nullable=False)
    notify_in_app = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
