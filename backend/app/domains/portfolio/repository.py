from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owned(self, user_id: UUID) -> Sequence[Portfolio]:
        query = select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.created_at.desc())
        return (await self._session.execute(query)).scalars().all()

    async def owned_one(self, user_id: UUID, portfolio_id: UUID) -> Portfolio | None:
        query = select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def add(self, portfolio: Portfolio) -> Portfolio:
        self._session.add(portfolio)
        return await self.save(portfolio)

    async def save(self, portfolio: Portfolio) -> Portfolio:
        await self._session.flush()
        await self._session.refresh(portfolio)
        return portfolio

    async def delete(self, portfolio: Portfolio) -> None:
        """Supprime le portefeuille ; la base supprime ses actifs et leurs transactions (ON DELETE CASCADE)."""
        await self._session.delete(portfolio)
        await self._session.flush()


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owned(self, user_id: UUID) -> Select[Asset]:
        owned = select(Portfolio.id).where(Portfolio.user_id == user_id)
        return select(Asset).where(Asset.portfolio_id.in_(owned))

    async def listed(self, user_id: UUID, portfolio_id: UUID | None) -> Sequence[Asset]:
        """Actifs de l'utilisateur hors crowdfunding, géré par ses propres routes, triés par symbole."""
        query = self._owned(user_id).where(Asset.asset_type != AssetType.CROWDFUNDING)
        if portfolio_id is not None:
            query = query.where(Asset.portfolio_id == portfolio_id)
        return (await self._session.execute(query.order_by(Asset.symbol))).scalars().all()

    async def listed_all(self, user_id: UUID, portfolio_id: UUID | None) -> Sequence[Asset]:
        """Tous les actifs de l'utilisateur, crowdfunding compris."""
        query = self._owned(user_id)
        if portfolio_id is not None:
            query = query.where(Asset.portfolio_id == portfolio_id)
        return (await self._session.execute(query)).scalars().all()

    async def owned_one(self, user_id: UUID, asset_id: UUID) -> Asset | None:
        return (await self._session.execute(self._owned(user_id).where(Asset.id == asset_id))).scalar_one_or_none()

    async def exists(self, portfolio_id: UUID, symbol: str, exchange: str) -> bool:
        query = select(Asset.id).where(
            Asset.portfolio_id == portfolio_id, Asset.symbol == symbol, Asset.exchange == exchange
        )
        return (await self._session.execute(query)).first() is not None

    async def on_platform(self, source: Asset, exchange: str) -> Asset:
        """Actif du même symbole dans le même portefeuille sur ``exchange``, créé vide s'il n'existe pas."""
        query = select(Asset).where(
            Asset.portfolio_id == source.portfolio_id, Asset.symbol == source.symbol, Asset.exchange == exchange
        )
        existing = (await self._session.execute(query)).scalar_one_or_none()
        if existing is not None:
            return existing
        created = Asset(
            portfolio_id=source.portfolio_id,
            symbol=source.symbol,
            name=source.name,
            asset_type=source.asset_type,
            quantity=Decimal("0"),
            avg_buy_price=Decimal("0"),
            exchange=exchange,
            currency=source.currency,
        )
        self._session.add(created)
        await self._session.flush()
        return created

    async def relabel_transactions(self, asset: Asset, exchange: str) -> None:
        """Les transactions qui nomment leur plateforme suivent l'actif sur sa nouvelle plateforme."""
        await self._session.execute(
            update(Transaction)
            .where(Transaction.asset_id == asset.id, func.coalesce(func.trim(Transaction.exchange), "") != "")
            .values(exchange=exchange or None)
        )

    async def by_id(self, asset_id: UUID) -> Asset:
        return await self._session.get_one(Asset, asset_id)

    async def add(self, asset: Asset) -> Asset:
        self._session.add(asset)
        return await self.save(asset)

    async def save(self, asset: Asset) -> Asset:
        await self._session.flush()
        await self._session.refresh(asset)
        return asset

    async def delete(self, asset: Asset) -> None:
        """Supprime l'actif ; la base supprime ses transactions et détache les transferts liés (ON DELETE)."""
        await self._session.delete(asset)
        await self._session.flush()
