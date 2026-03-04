"""Prediction log model for tracking predictions and calibration."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String
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

    # Calibration fields
    predicted_price = Column(Float, nullable=True)
    price_at_creation = Column(Numeric(18, 8), nullable=True)  # Baseline for direction tracking
    target_date = Column(DateTime, nullable=True, index=True)
    horizon_days = Column(Integer, nullable=True)
    actual_price = Column(Float, nullable=True)  # Filled later by calibration task
    error_pct = Column(Float, nullable=True)  # |predicted - actual| / actual * 100
    models_detail = Column(JSON, nullable=True)

    # CI tracking (filled at prediction time)
    confidence_low = Column(Float, nullable=True)
    confidence_high = Column(Float, nullable=True)

    # Accuracy tracking (filled by check_prediction_accuracy task)
    accuracy_checked = Column(DateTime, nullable=True)
    mape = Column(Float, nullable=True)  # Mean Absolute Percentage Error
    direction_correct = Column(Boolean, nullable=True)  # Did we predict the right direction?
    ci_covered = Column(Boolean, nullable=True)  # Was actual price within CI?

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
