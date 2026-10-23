from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fx.models import FxDailyRate

_rates = FxDailyRate.__table__


class FxRateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def series(self, base: str, quote: str) -> list[tuple[date, Decimal]]:
        query = (
            select(_rates.c.rate_date, _rates.c.rate)
            .where(_rates.c.base_currency == base, _rates.c.quote_currency == quote)
            .order_by(_rates.c.rate_date)
        )
        return [(day, Decimal(str(rate))) for day, rate in (await self._session.execute(query)).all()]

    async def last_date(self, base: str, quote: str) -> date | None:
        query = select(func.max(_rates.c.rate_date)).where(
            _rates.c.base_currency == base, _rates.c.quote_currency == quote
        )
        last: date | None = (await self._session.execute(query)).scalar()
        return last

    async def insert_missing(self, base: str, quote: str, rates: dict[date, Decimal]) -> int:
        if not rates:
            return 0
        values = [
            {"rate_date": day, "base_currency": base, "quote_currency": quote, "rate": rate, "source": "ecb"}
            for day, rate in rates.items()
        ]
        statement = insert(FxDailyRate).values(values).on_conflict_do_nothing(constraint="uq_fx_daily_rates_date_pair")
        result = await self._session.execute(statement)
        await self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)
