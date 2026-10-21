from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.market_data.history.series import PriceSeries
from app.domains.portfolio.models import Asset, AssetType
from app.models.transaction import Transaction

_history = AssetPriceHistory.__table__
_assets = Asset.__table__
_transactions = Transaction.__table__
QUOTED_TYPES = (AssetType.CRYPTO, AssetType.STOCK, AssetType.ETF)
CHUNK = 500


def _volumes(values: list[Decimal | None]) -> list[float] | None:
    known = [float(v) for v in values if v is not None]
    return known if len(known) == len(values) else None


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def series(self, symbols: Sequence[str], since: date) -> dict[str, PriceSeries]:
        if not symbols:
            return {}
        query = (
            select(_history.c.symbol, _history.c.price_date, _history.c.price_eur, _history.c.volume)
            .where(_history.c.symbol.in_(symbols), _history.c.price_date >= since)
            .order_by(_history.c.symbol, _history.c.price_date)
        )
        rows: dict[str, list[tuple[date, Decimal, Decimal | None]]] = {}
        for symbol, day, price, volume in (await self._session.execute(query)).all():
            rows.setdefault(symbol, []).append((day, price, volume))
        return {
            symbol: PriceSeries(
                dates=[datetime.combine(day, datetime.min.time()) for day, _, _ in points],
                prices=[float(price) for _, price, _ in points],
                volumes=_volumes([v for _, _, v in points]),
            )
            for symbol, points in rows.items()
        }

    async def upsert(self, symbol: str, series: PriceSeries, source: str) -> int:
        rows: dict[date, dict[str, object]] = {}
        volumes: list[float | None] = (
            list(series.volumes) if series.volumes is not None else [None] * len(series.prices)
        )
        for moment, price, volume in zip(series.dates, series.prices, volumes, strict=True):
            rows[moment.date()] = {
                "symbol": symbol,
                "price_date": moment.date(),
                "price_eur": Decimal(str(price)),
                "volume": Decimal(str(volume)) if volume is not None else None,
                "source": source,
            }
        values = list(rows.values())
        for start in range(0, len(values), CHUNK):
            statement = insert(AssetPriceHistory).values(values[start : start + CHUNK])
            statement = statement.on_conflict_do_update(
                constraint="uq_symbol_price_date",
                set_={
                    "price_eur": statement.excluded.price_eur,
                    "volume": statement.excluded.volume,
                    "source": statement.excluded.source,
                },
            )
            await self._session.execute(statement)
        await self._session.flush()
        return len(values)

    async def mirror_current_price(self, symbol: str, price: float) -> None:
        statement = (
            update(Asset)
            .where(Asset.symbol == symbol, Asset.asset_type != AssetType.CROWDFUNDING)
            .values(current_price=Decimal(str(price)), last_price_update=datetime.now(UTC))
        )
        await self._session.execute(statement)

    async def last_days(self) -> dict[str, date]:
        query = select(_history.c.symbol, func.max(_history.c.price_date)).group_by(_history.c.symbol)
        return {symbol: day for symbol, day in (await self._session.execute(query)).all()}

    async def counts(self) -> dict[str, int]:
        query = select(_history.c.symbol, func.count()).group_by(_history.c.symbol)
        return {symbol: count for symbol, count in (await self._session.execute(query)).all()}

    async def known_days(self, symbol: str, start: date, end: date) -> set[date]:
        query = select(_history.c.price_date).where(
            _history.c.symbol == symbol, _history.c.price_date >= start, _history.c.price_date <= end
        )
        return set((await self._session.execute(query)).scalars())

    async def quoted_holdings(self) -> list[tuple[str, str]]:
        query = (
            select(_assets.c.symbol, _assets.c.asset_type)
            .where(_assets.c.quantity > 0, _assets.c.asset_type.in_(QUOTED_TYPES))
            .distinct()
        )
        return [(symbol.upper(), kind.value) for symbol, kind in (await self._session.execute(query)).all()]

    async def first_crypto_trades(self) -> list[tuple[str, datetime]]:
        first = func.min(func.coalesce(_transactions.c.executed_at, _transactions.c.created_at))
        query = (
            select(_assets.c.symbol, first)
            .join(_transactions, _transactions.c.asset_id == _assets.c.id)
            .where(_assets.c.quantity > 0, _assets.c.asset_type == AssetType.CRYPTO)
            .group_by(_assets.c.symbol)
        )
        return [(symbol.upper(), moment) for symbol, moment in (await self._session.execute(query)).all() if moment]
