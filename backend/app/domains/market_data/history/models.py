import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base


class AssetPriceHistory(Base):
    __tablename__ = "asset_price_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_eur: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(precision=30, scale=8), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="coingecko")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "price_date", name="uq_symbol_price_date"),
        Index("ix_asset_price_history_symbol_date", "symbol", "price_date"),
    )
