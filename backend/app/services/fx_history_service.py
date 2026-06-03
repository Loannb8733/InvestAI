"""DB-backed historical FX service (FIN-01).

Reads daily reference rates from ``fx_daily_rates`` and resolves the rate effective on a
given date via forward-fill (see ``fx_history.resolve_rate``). Can seed/refresh the table
from Frankfurter (ECB data, free, no key).

Convention: ``get_rate(d, "USD", "EUR")`` returns EUR per 1 USD (≈ 0.92), matching the
``Transaction.conversion_rate`` multiplier the cost-basis engine expects. Frankfurter
rebases natively, so requesting ``base=USD&symbols=EUR`` already yields EUR-per-USD — no
inversion needed at seed time.

The read path (``get_rate``) is network-free; only ``seed_range`` hits Frankfurter. This
keeps the live sync and the backfill deterministic once the table is populated.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fx_rate import FxDailyRate
from app.services.fx_history import resolve_rate

logger = logging.getLogger(__name__)

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


class FxHistoryService:
    """Resolve and seed historical FX rates backed by ``fx_daily_rates``."""

    def __init__(self, db: AsyncSession):
        self.db = db
        # Per-instance memoization of (from,to) -> sorted [(date, rate)] to avoid
        # re-querying within a single backfill/sync run.
        self._cache: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}

    async def _load_pair(self, from_ccy: str, to_ccy: str) -> list[tuple[date, Decimal]]:
        key = (from_ccy.upper(), to_ccy.upper())
        if key in self._cache:
            return self._cache[key]
        rows = await self.db.execute(
            select(FxDailyRate.rate_date, FxDailyRate.rate)
            .where(
                FxDailyRate.base_currency == key[0],
                FxDailyRate.quote_currency == key[1],
            )
            .order_by(FxDailyRate.rate_date.asc())
        )
        sorted_rates = [(d, Decimal(str(r))) for d, r in rows.all()]
        self._cache[key] = sorted_rates
        return sorted_rates

    async def get_rate(self, rate_date: date, from_ccy: str, to_ccy: str) -> Optional[Decimal]:
        """Return ``to_ccy`` per 1 ``from_ccy`` on ``rate_date`` (forward-filled).

        Same currency returns 1. Returns ``None`` when no rate at/<= the date exists
        (caller must decide how to handle missing history — never silently assume 1).
        """
        if from_ccy.upper() == to_ccy.upper():
            return Decimal("1")
        sorted_rates = await self._load_pair(from_ccy, to_ccy)
        return resolve_rate(rate_date, sorted_rates)

    async def seed_range(
        self,
        from_ccy: str,
        to_ccy: str,
        start: date,
        end: date,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> int:
        """Fetch the daily series for ``from_ccy->to_ccy`` and upsert missing dates.

        Idempotent: existing (date, base, quote) rows are left untouched (ON CONFLICT DO
        NOTHING). Returns the number of rows inserted. Invalidates the in-memory cache for
        the pair so subsequent ``get_rate`` calls see the new data.
        """
        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()
        url = f"{FRANKFURTER_BASE_URL}/{start.isoformat()}..{end.isoformat()}"
        params = {"base": from_ccy, "symbols": to_ccy}

        owns_client = client is None
        client = client or httpx.AsyncClient(timeout=15.0)
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns_client:
                await client.aclose()

        rates: dict = data.get("rates", {}) or {}
        if not rates:
            logger.warning("Frankfurter returned no rates for %s->%s %s..%s", from_ccy, to_ccy, start, end)
            return 0

        records = []
        for day_str, by_symbol in rates.items():
            value = by_symbol.get(to_ccy)
            if value is None:
                continue
            records.append(
                {
                    "rate_date": date.fromisoformat(day_str),
                    "base_currency": from_ccy,
                    "quote_currency": to_ccy,
                    "rate": Decimal(str(value)),
                    "source": "ecb",
                }
            )

        if not records:
            return 0

        stmt = pg_insert(FxDailyRate).values(records)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_fx_daily_rates_date_pair")
        result = await self.db.execute(stmt)
        await self.db.commit()
        # Invalidate cache for this pair.
        self._cache.pop((from_ccy, to_ccy), None)
        return result.rowcount or 0

    async def ensure_seeded(
        self,
        from_ccy: str,
        to_ccy: str,
        earliest: date,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> int:
        """Seed full history on first run, then only top up the tail to today.

        Cheap to call on every sync: when the table already covers up to ``today`` it
        does nothing; otherwise it fetches only the missing ``[max_date .. today]`` window
        (or ``[earliest .. today]`` when the pair is empty). Returns rows inserted.
        """
        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()
        res = await self.db.execute(
            select(func.max(FxDailyRate.rate_date)).where(
                FxDailyRate.base_currency == from_ccy,
                FxDailyRate.quote_currency == to_ccy,
            )
        )
        max_d = res.scalar()
        today = date.today()
        if max_d is None:
            return await self.seed_range(from_ccy, to_ccy, earliest, today, client=client)
        if max_d < today:
            return await self.seed_range(from_ccy, to_ccy, max_d, today, client=client)
        return 0
