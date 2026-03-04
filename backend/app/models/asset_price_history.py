"""Persistent historical price data model.

Stores daily closing prices fetched from CoinGecko/Yahoo Finance
so we don't rely solely on Redis cache for historical data.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class AssetPriceHistory(Base):
    __tablename__ = "asset_price_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    price_date = Column(Date, nullable=False)
    price_eur = Column(Numeric(precision=18, scale=8), nullable=False)
    source = Column(String(30), nullable=False, default="coingecko")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "price_date", name="uq_symbol_price_date"),
        Index("ix_asset_price_history_symbol_date", "symbol", "price_date"),
    )
