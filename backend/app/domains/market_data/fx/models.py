import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class FxDailyRate(Base):
    __tablename__ = "fx_daily_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=24, scale=12), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="ecb")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_fx_daily_rates_date_pair"),
        Index("ix_fx_daily_rates_pair_date", "base_currency", "quote_currency", "rate_date"),
    )
