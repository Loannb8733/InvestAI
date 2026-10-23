import logging
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.exchanges.sync.symbols import base_symbol
from app.domains.market_data.history.tasks import schedule_refresh
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions import ledger
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)

WITHDRAWAL_WINDOW = timedelta(days=1)


class Book:
    """Actifs d'un exchange (un actif sans plateforme est adopté) et écritures d'une synchronisation, sans doublon."""

    def __init__(self, session: AsyncSession, portfolio: Portfolio, exchange: str) -> None:
        self.session = session
        self.portfolio = portfolio
        self.exchange = exchange
        self.written = 0
        self._assets: dict[str, Asset] = {}
        self._seen: set[str] = set()
        self._touched: dict[str, Asset] = {}
        self._transactions = TransactionRepository(session)

    @classmethod
    async def open(cls, session: AsyncSession, portfolio: Portfolio, exchange: str) -> "Book":
        book = cls(session, portfolio, exchange)
        assets = (await session.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))).scalars().all()
        for asset in sorted(assets, key=lambda a: a.exchange != exchange):
            if asset.exchange in (exchange, "") and asset.symbol not in book._assets:
                book._assets[asset.symbol] = asset
        if book._assets:
            query = select(Transaction.external_id).where(
                Transaction.asset_id.in_([a.id for a in book._assets.values()]), Transaction.external_id.isnot(None)
            )
            book._seen = {str(x) for x in (await session.execute(query)).scalars()}
        return book

    def adopt(self) -> None:
        """Range sur la plateforme de l'exchange les actifs sans plateforme qu'il reprend."""
        for asset in self._assets.values():
            asset.exchange = self.exchange

    @property
    def symbols(self) -> list[str]:
        return list(self._assets)

    @property
    def assets(self) -> Sequence[Asset]:
        return list(self._assets.values())

    def held(self, symbol: str) -> Asset | None:
        return self._assets.get(base_symbol(symbol))

    def knows(self, *external_ids: str) -> bool:
        return any(x in self._seen for x in external_ids)

    def remember(self, external_id: str) -> None:
        self._seen.add(external_id)

    async def asset(self, symbol: str) -> Asset:
        """Actif de l'exchange pour ce symbole, créé au besoin avec son historique de cours."""
        base = base_symbol(symbol)
        found = self._assets.get(base)
        if found is not None:
            return found
        asset = Asset(
            portfolio_id=self.portfolio.id,
            symbol=base,
            name=base,
            asset_type=AssetType.CRYPTO,
            quantity=ledger.ZERO,
            avg_buy_price=ledger.ZERO,
            currency="EUR",
            exchange=self.exchange,
        )
        self.session.add(asset)
        await self.session.flush()
        self._assets[base] = asset
        schedule_refresh(base, "crypto")
        return asset

    async def record(
        self,
        asset: Asset,
        kind: TransactionType,
        quantity: Decimal,
        price: Decimal,
        *,
        executed_at: datetime,
        external_id: str | None = None,
        currency: str = "EUR",
        rate: Decimal | None = None,
        fee: Decimal = ledger.ZERO,
        fee_currency: str | None = None,
        notes: str | None = None,
    ) -> Transaction | None:
        """Écrit l'opération et en applique l'effet ; rend None pour une opération déjà connue."""
        if external_id is not None and external_id in self._seen:
            return None
        transaction = Transaction(
            asset_id=asset.id,
            transaction_type=kind,
            quantity=quantity,
            price=price,
            fee=fee,
            fee_currency=fee_currency,
            currency=currency,
            conversion_rate=rate,
            executed_at=executed_at,
            exchange=self.exchange,
            external_id=external_id,
            notes=notes,
        )
        if external_id is not None:
            self._seen.add(external_id)
        if await self._transactions.hash_taken(transaction.compute_hash()):
            return None
        try:
            async with self.session.begin_nested():
                self.session.add(transaction)
        except IntegrityError:
            logger.info("Opération %s écrite entre-temps par une autre synchronisation", transaction.internal_hash)
            return None
        asset.quantity = ledger.moved(asset.quantity, kind, quantity)
        self._touched[asset.symbol] = asset
        self.written += 1
        return transaction

    async def repair(self, external_ids: Iterable[str], price: Decimal, currency: str, rate: Decimal | None) -> bool:
        """Corrige prix, devise et taux des opérations déjà importées sous ces identifiants."""
        query = select(Transaction).where(Transaction.external_id.in_([x for x in external_ids if x]))
        changed = False
        for row in (await self.session.execute(query)).scalars():
            if price and row.price != price:
                row.price = price
                changed = True
            if (row.currency, row.conversion_rate) != (currency, rate):
                row.currency, row.conversion_rate = currency, rate
                changed = True
        return changed

    async def moved_since(self, asset: Asset, since: datetime) -> list[Decimal]:
        query = select(Transaction.quantity).where(Transaction.asset_id == asset.id, Transaction.executed_at >= since)
        return list((await self.session.execute(query)).scalars())

    async def withdrawn_around(self, asset: Asset, moment: datetime) -> list[Decimal]:
        query = select(Transaction.quantity).where(
            Transaction.asset_id == asset.id,
            Transaction.transaction_type == TransactionType.TRANSFER_OUT,
            Transaction.executed_at.between(moment - WITHDRAWAL_WINDOW, moment + WITHDRAWAL_WINDOW),
        )
        return list((await self.session.execute(query)).scalars())

    async def refresh_cost(self, asset: Asset) -> None:
        await self.session.flush()
        asset.avg_buy_price = await self._transactions.cost_basis(asset.id)

    async def close(self) -> None:
        """Recalcule le prix de revient des actifs touchés, à la règle du domaine transactions."""
        for asset in self._touched.values():
            await self.refresh_cost(asset)


def now() -> datetime:
    return datetime.now(UTC)
