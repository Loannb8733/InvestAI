"""Asset model."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class AssetType(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    REAL_ESTATE = "real_estate"
    BOND = "bond"
    CROWDFUNDING = "crowdfunding"
    OTHER = "other"


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", "exchange", name="uq_assets_portfolio_symbol_exchange"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    asset_type = Column(Enum(AssetType), nullable=False)
    quantity = Column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)
    avg_buy_price = Column(Numeric(precision=18, scale=8), default=Decimal("0"), nullable=False)
    current_price = Column(Numeric(precision=18, scale=8), nullable=True)
    exchange = Column(String(50), nullable=False, default="", server_default="")
    currency = Column(String(10), default="EUR", nullable=False)
    last_price_update = Column(DateTime(timezone=True), nullable=True)

    # Crowdfunding / real-estate specific fields
    interest_rate = Column(Numeric(precision=6, scale=3), nullable=True)  # annual %
    maturity_date = Column(Date, nullable=True)
    project_status = Column(String(20), nullable=True)  # active, completed, delayed, defaulted
    invested_amount = Column(Numeric(precision=12, scale=2), nullable=True)  # initial EUR amount

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
