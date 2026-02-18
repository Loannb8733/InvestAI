"""Notification model."""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class NotificationType(str, enum.Enum):
    ALERT_TRIGGERED = "alert_triggered"
    PRICE_UPDATE = "price_update"
    SYSTEM = "system"
    PORTFOLIO_UPDATE = "portfolio_update"
    REPORT_READY = "report_ready"


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.NORMAL, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
