import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class PredictionLog(Base):
    """Prévision journalisée, complétée plus tard par le cours réel pour mesurer erreur, direction et couverture."""

    __tablename__ = "prediction_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prediction_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    predicted_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_at_creation: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    models_detail: Mapped[Any] = mapped_column(JSON, nullable=True)
    confidence_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mape: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ci_covered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
