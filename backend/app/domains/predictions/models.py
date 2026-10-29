import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text
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


class PlannedOrderStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class PlannedOrder(Base):
    """Ordre marqué pour exécution depuis un signal alpha, par Telegram ou par l'application."""

    __tablename__ = "planned_orders"
    __table_args__ = (CheckConstraint("order_eur >= 0", name="ck_planned_orders_amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    order_eur: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default=0)
    alpha_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prob_ruin_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_ruin_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="telegram")
    status: Mapped[PlannedOrderStatus] = mapped_column(
        Enum(PlannedOrderStatus), nullable=False, default=PlannedOrderStatus.PENDING
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
