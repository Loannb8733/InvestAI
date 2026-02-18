"""Prediction log model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.models import Base


class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(20), nullable=False, index=True)
    asset_type = Column(String(20), nullable=False)
    model_name = Column(String(100), nullable=False)
    prediction_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
