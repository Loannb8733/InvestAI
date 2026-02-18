"""Portfolio snapshot model."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    snapshot_date = Column(DateTime(timezone=True), nullable=False)
    total_value = Column(Numeric(precision=18, scale=2), nullable=False)
    total_invested = Column(Numeric(precision=18, scale=2), nullable=False)
    total_gain_loss = Column(Numeric(precision=18, scale=2), nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
