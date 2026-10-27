import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class AlertCondition(enum.StrEnum):
    """Condition d'alerte ; les trois dernières portent sur le portefeuille entier, sans actif."""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    CHANGE_PERCENT_UP = "change_percent_up"
    CHANGE_PERCENT_DOWN = "change_percent_down"
    DAILY_CHANGE_UP = "daily_change_up"
    DAILY_CHANGE_DOWN = "daily_change_down"
    TARGET_BREAK_EVEN = "target_break_even"
    VOLATILITY_SPIKE = "volatility_spike"
    PORTFOLIO_DRAWDOWN = "portfolio_drawdown"
    CONCENTRATION_HHI = "concentration_hhi"
    ALLOCATION_DRIFT = "allocation_drift"


PORTFOLIO_CONDITIONS = frozenset(
    {AlertCondition.PORTFOLIO_DRAWDOWN, AlertCondition.CONCENTRATION_HHI, AlertCondition.ALLOCATION_DRIFT}
)
AUTO_THRESHOLD_CONDITIONS = frozenset({AlertCondition.TARGET_BREAK_EVEN, AlertCondition.VOLATILITY_SPIKE})


class Alert(Base):
    """Alerte d'un utilisateur, sur un actif ou sur son portefeuille."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    condition: Mapped[AlertCondition] = mapped_column(Enum(AlertCondition), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_in_app: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
