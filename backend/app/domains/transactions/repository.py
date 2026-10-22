from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, delete, func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, Portfolio
from app.domains.transactions.ledger import COST_BASIS_TYPES
from app.domains.transactions.models import Transaction, TransactionType

MANUAL_PLATFORM = "manuel"


@dataclass(frozen=True)
class TransactionFilters:
    portfolio_id: UUID | None = None
    asset_id: UUID | None = None
    types: tuple[TransactionType, ...] = ()
    exchange: str | None = None
    asset_symbol: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


def _effective_exchange() -> ColumnElement[str | None]:
    return func.coalesce(func.nullif(func.trim(Transaction.exchange), ""), func.nullif(func.trim(Asset.exchange), ""))


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owned(self, user_id: UUID) -> Select[Transaction, Asset]:
        return (
            select(Transaction, Asset)
            .join(Asset, Transaction.asset_id == Asset.id)
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(Portfolio.user_id == user_id)
        )

    def _filtered(self, user_id: UUID, filters: TransactionFilters) -> Select[Transaction, Asset]:
        query = self._owned(user_id)
        if filters.portfolio_id is not None:
            query = query.where(Asset.portfolio_id == filters.portfolio_id)
        if filters.asset_id is not None:
            query = query.where(Transaction.asset_id == filters.asset_id)
        if filters.types:
            query = query.where(Transaction.transaction_type.in_(filters.types))
        if filters.date_from is not None:
            query = query.where(Transaction.executed_at >= datetime.combine(filters.date_from, time.min, tzinfo=UTC))
        if filters.date_to is not None:
            query = query.where(Transaction.executed_at <= datetime.combine(filters.date_to, time.max, tzinfo=UTC))
        if filters.exchange is not None:
            exchange = filters.exchange.strip().lower()
            if exchange in ("", MANUAL_PLATFORM):
                query = query.where(_effective_exchange().is_(None))
            else:
                query = query.where(func.lower(_effective_exchange()) == exchange)
        if filters.asset_symbol:
            query = query.where(func.upper(Asset.symbol) == filters.asset_symbol.strip().upper())
        if filters.search and filters.search.strip():
            pattern = _like(filters.search.strip())
            query = query.where(
                or_(Asset.symbol.ilike(pattern, escape="\\"), Transaction.notes.ilike(pattern, escape="\\"))
            )
        return query

    def _newest_first(self, user_id: UUID, filters: TransactionFilters) -> Select[Transaction, Asset]:
        return self._filtered(user_id, filters).order_by(
            func.coalesce(Transaction.executed_at, Transaction.created_at).desc()
        )

    async def page(
        self, user_id: UUID, filters: TransactionFilters, *, skip: int, limit: int
    ) -> Sequence[tuple[Transaction, Asset]]:
        """Transactions filtrées, les plus récentes d'abord ; une transaction sans date compte à sa création."""
        rows = await self._session.execute(self._newest_first(user_id, filters).offset(skip).limit(limit))
        return [row.tuple() for row in rows.all()]

    async def count(self, user_id: UUID, filters: TransactionFilters) -> int:
        query = select(func.count()).select_from(self._filtered(user_id, filters).subquery())
        return int((await self._session.execute(query)).scalar() or 0)

    async def all_with_assets(self, user_id: UUID, portfolio_id: UUID | None) -> Sequence[tuple[Transaction, Asset]]:
        rows = await self._session.execute(self._newest_first(user_id, TransactionFilters(portfolio_id=portfolio_id)))
        return [row.tuple() for row in rows.all()]

    async def owned_one(self, user_id: UUID, transaction_id: UUID) -> Transaction | None:
        row = (await self._session.execute(self._owned(user_id).where(Transaction.id == transaction_id))).first()
        return row.tuple()[0] if row else None

    async def get(self, transaction_id: UUID) -> Transaction | None:
        return await self._session.get(Transaction, transaction_id)

    async def hash_taken(self, internal_hash: str, *, other_than: UUID | None = None) -> bool:
        query = select(Transaction.id).where(Transaction.internal_hash == internal_hash)
        if other_than is not None:
            query = query.where(Transaction.id != other_than)
        return (await self._session.execute(query)).first() is not None

    async def cost_basis(self, asset_id: UUID) -> Decimal:
        """Prix de revient moyen : achats, conversions et transferts entrants à prix connu, frais compris."""
        query = select(
            func.sum(Transaction.quantity * Transaction.price + Transaction.fee), func.sum(Transaction.quantity)
        ).where(
            Transaction.asset_id == asset_id,
            Transaction.transaction_type.in_(COST_BASIS_TYPES),
            Transaction.price > 0,
        )
        total, quantity = (await self._session.execute(query)).one()
        return Decimal(total) / Decimal(quantity) if quantity else Decimal("0")

    async def platforms(self, user_id: UUID) -> list[str]:
        """Plateformes des transactions et des actifs de l'utilisateur, sans doublon de casse."""
        owned = Portfolio.user_id == user_id
        from_transactions = (
            select(func.trim(Transaction.exchange).label("name"))
            .join(Asset, Transaction.asset_id == Asset.id)
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(owned, func.trim(Transaction.exchange) != "")
        )
        from_assets = (
            select(func.trim(Asset.exchange).label("name"))
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(owned, func.trim(Asset.exchange) != "")
        )
        names = (await self._session.execute(select(union(from_transactions, from_assets).subquery().c.name))).scalars()
        seen: dict[str, str] = {}
        for name in names:
            seen.setdefault(name.lower(), name)
        return sorted(seen.values())

    def add(self, transaction: Transaction) -> None:
        self._session.add(transaction)

    async def flush(self) -> None:
        await self._session.flush()

    async def delete(self, transaction: Transaction) -> None:
        await self._session.delete(transaction)
        await self._session.flush()

    async def delete_for_assets(self, asset_ids: Sequence[UUID]) -> int:
        count = (
            await self._session.execute(select(func.count()).where(Transaction.asset_id.in_(asset_ids)))
        ).scalar() or 0
        await self._session.execute(
            update(Transaction).where(Transaction.asset_id.in_(asset_ids)).values(related_transaction_id=None)
        )
        await self._session.execute(delete(Transaction).where(Transaction.asset_id.in_(asset_ids)))
        return int(count)
