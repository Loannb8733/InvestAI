import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base

CROWDFUNDING_KIND = "crowdfunding"


class AssetType(enum.StrEnum):
    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    REAL_ESTATE = "real_estate"
    BOND = "bond"
    CROWDFUNDING = "crowdfunding"
    OTHER = "other"


class Portfolio(Base):
    """Portefeuille d'un utilisateur.

    ``kind`` vaut ``CROWDFUNDING_KIND`` pour le portefeuille que l'application gère
    elle-même, None sinon : le nom reste un libellé libre.
    """

    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    cash_balances: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Asset(Base):
    """Position d'un portefeuille sur une plateforme ; de ``interest_rate`` à ``invested_amount`` : crowdfunding."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", "exchange", name="uq_assets_portfolio_symbol_exchange"),
        CheckConstraint("quantity >= 0", name="ck_assets_quantity_positive"),
        CheckConstraint("avg_buy_price >= 0", name="ck_assets_avg_buy_price_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(precision=24, scale=8), default=Decimal("0"), nullable=False)
    avg_buy_price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), default=Decimal("0"), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=8), nullable=True)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    last_price_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(precision=6, scale=3), nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    invested_amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
