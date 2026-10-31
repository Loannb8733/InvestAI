import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class PortfolioSnapshot(Base):
    """Valeur d'un portefeuille, ou de tout le compte sans `portfolio_id`, un seul instantané par jour."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    total_invested: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    total_gain_loss: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "uq_portfolio_snapshots_user_day_global",
            "user_id",
            text("((snapshot_date AT TIME ZONE 'UTC')::date)"),
            unique=True,
            postgresql_where=text("portfolio_id IS NULL"),
        ),
        Index(
            "uq_portfolio_snapshots_user_portfolio_day",
            "user_id",
            "portfolio_id",
            text("((snapshot_date AT TIME ZONE 'UTC')::date)"),
            unique=True,
            postgresql_where=text("portfolio_id IS NOT NULL"),
        ),
    )
