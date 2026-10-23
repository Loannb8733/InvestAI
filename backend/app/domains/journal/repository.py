from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.journal.models import Note
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset, Portfolio

SCORED_SENTIMENTS = ("bullish", "bearish", "neutral")

_assets = Asset.__table__
_portfolios = Portfolio.__table__
_prices = AssetPriceHistory.__table__


@dataclass(frozen=True)
class AssetRef:
    id: UUID
    symbol: str | None
    name: str | None
    current_price: Decimal | None


@dataclass
class PriceSeries:
    dates: list[date] = field(default_factory=list)
    prices: list[Decimal] = field(default_factory=list)


@dataclass(frozen=True)
class NoteFilters:
    tag: str | None = None
    asset_id: UUID | None = None
    search: str | None = None
    skip: int = 0
    limit: int = 50


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, user_id: UUID, filters: NoteFilters) -> Sequence[Note]:
        query = select(Note).where(Note.user_id == user_id)
        if filters.asset_id:
            query = query.where(Note.asset_id == filters.asset_id)
        if filters.tag:
            query = query.where(Note.tags.ilike(f"%{filters.tag}%"))
        if filters.search:
            pattern = f"%{filters.search}%"
            query = query.where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
        query = query.order_by(Note.created_at.desc()).offset(filters.skip).limit(filters.limit)
        return (await self._session.execute(query)).scalars().all()

    async def list_all(self, user_id: UUID) -> Sequence[Note]:
        return (await self._session.execute(select(Note).where(Note.user_id == user_id))).scalars().all()

    async def list_scorable(self, user_id: UUID) -> Sequence[Note]:
        query = (
            select(Note)
            .where(Note.user_id == user_id, Note.asset_id.isnot(None), Note.sentiment.in_(SCORED_SENTIMENTS))
            .order_by(Note.created_at.desc())
        )
        return (await self._session.execute(query)).scalars().all()

    async def get_owned(self, note_id: UUID, user_id: UUID) -> Note | None:
        query = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def add(self, note: Note) -> Note:
        self._session.add(note)
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def save(self, note: Note) -> Note:
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)
        await self._session.flush()

    async def find_owned_asset(self, asset_id: UUID, user_id: UUID) -> AssetRef | None:
        query = (
            select(_assets.c.id, _assets.c.symbol, _assets.c.name, _assets.c.current_price)
            .join(_portfolios, _portfolios.c.id == _assets.c.portfolio_id)
            .where(_assets.c.id == asset_id, _portfolios.c.user_id == user_id)
        )
        row = (await self._session.execute(query)).first()
        return AssetRef(row.id, row.symbol, row.name, row.current_price) if row else None

    async def assets_by_id(self, asset_ids: set[UUID]) -> dict[UUID, AssetRef]:
        if not asset_ids:
            return {}
        query = select(_assets.c.id, _assets.c.symbol, _assets.c.name, _assets.c.current_price).where(
            _assets.c.id.in_(asset_ids)
        )
        rows = (await self._session.execute(query)).all()
        return {row.id: AssetRef(row.id, row.symbol, row.name, row.current_price) for row in rows}

    async def price_history(self, symbols: set[str], since: date) -> dict[str, PriceSeries]:
        if not symbols:
            return {}
        query = (
            select(_prices.c.symbol, _prices.c.price_date, _prices.c.price_eur)
            .where(_prices.c.symbol.in_(symbols), _prices.c.price_date >= since)
            .order_by(_prices.c.symbol, _prices.c.price_date)
        )
        history: dict[str, PriceSeries] = {}
        for symbol, price_date, price_eur in (await self._session.execute(query)).all():
            series = history.setdefault(symbol, PriceSeries())
            series.dates.append(price_date)
            series.prices.append(price_eur)
        return history
