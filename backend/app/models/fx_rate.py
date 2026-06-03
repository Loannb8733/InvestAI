"""Daily FX reference rate model (FIN-01).

Persists ECB daily reference rates (sourced via Frankfurter) so the exchange sync and
the historical backfill can resolve the FX rate at a trade's execution date without
hitting the network per trade. The cost-basis engine never reads this table directly —
it reads ``Transaction.conversion_rate``, which the sync/backfill fill from here.

Storage convention: one row per (date, base, quote) with ``rate`` = units of
``quote_currency`` per 1 unit of ``base_currency``. To get the "EUR per 1 USD" multiplier
the engine expects, store rows as base="USD", quote="EUR" (rate ≈ 0.92), matching the
``PriceService.get_forex_rate("USD", "EUR")`` convention.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class FxDailyRate(Base):
    __tablename__ = "fx_daily_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rate_date = Column(Date, nullable=False, index=True)
    base_currency = Column(String(10), nullable=False)
    quote_currency = Column(String(10), nullable=False)
    # quote units per 1 base unit (e.g. base=USD, quote=EUR, rate≈0.92).
    rate = Column(Numeric(precision=24, scale=12), nullable=False)
    source = Column(String(30), nullable=False, default="ecb")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_fx_daily_rates_date_pair"),
        Index("ix_fx_daily_rates_pair_date", "base_currency", "quote_currency", "rate_date"),
    )
