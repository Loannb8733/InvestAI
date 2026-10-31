"""Requêtes des instantanés et de la série de valeur."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction


async def user_transactions(db: AsyncSession, user_id: str) -> Sequence[Any]:
    """Transactions hors crowdfunding, avec symbole et type d'actif, de la plus ancienne à la plus récente."""
    portfolios = (await db.execute(select(Portfolio.id).where(Portfolio.user_id == user_id))).scalars().all()
    if not portfolios:
        return []
    result = await db.execute(
        select(
            Transaction.executed_at,
            Transaction.transaction_type,
            Transaction.quantity,
            Transaction.price,
            Transaction.fee,
            Transaction.currency,
            Transaction.conversion_rate,
            Asset.symbol,
            Asset.asset_type,
            Transaction.created_at,
        )
        .join(Asset, Transaction.asset_id == Asset.id)
        .where(Asset.portfolio_id.in_(portfolios), Asset.asset_type != AssetType.CROWDFUNDING)
        .order_by(Transaction.executed_at.asc())
    )
    return result.all()


async def global_snapshots_since(db: AsyncSession, user_id: str, since: datetime) -> Sequence[PortfolioSnapshot]:
    """Instantanés de tout le compte depuis une date, du plus ancien au plus récent."""
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.portfolio_id.is_(None),
            PortfolioSnapshot.snapshot_date >= since,
        )
        .order_by(PortfolioSnapshot.snapshot_date.asc())
    )
    return result.scalars().all()


async def users_with_portfolio(db: AsyncSession) -> list[str]:
    """Identifiants des utilisateurs ayant au moins un portefeuille."""
    result = await db.execute(select(User.id).where(User.id.in_(select(Portfolio.user_id).distinct())))
    return [str(user_id) for user_id in result.scalars().all()]


async def has_global_snapshot(db: AsyncSession, user_id: str, start: datetime, end: datetime) -> bool:
    """Dit si un instantané du compte existe sur l'intervalle."""
    result = await db.execute(
        select(func.count(PortfolioSnapshot.id)).where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.snapshot_date >= start,
            PortfolioSnapshot.snapshot_date < end,
            PortfolioSnapshot.portfolio_id.is_(None),
        )
    )
    return bool(result.scalar())


async def has_portfolio_snapshot(
    db: AsyncSession, user_id: str, portfolio_id: UUID, start: datetime, end: datetime
) -> bool:
    """Dit si un instantané du portefeuille existe sur l'intervalle."""
    result = await db.execute(
        select(func.count(PortfolioSnapshot.id)).where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date >= start,
            PortfolioSnapshot.snapshot_date < end,
        )
    )
    return bool(result.scalar())


async def count_older_than(db: AsyncSession, cutoff: datetime) -> int:
    """Nombre d'instantanés antérieurs à une date."""
    result = await db.execute(select(func.count(PortfolioSnapshot.id)).where(PortfolioSnapshot.snapshot_date < cutoff))
    return int(result.scalar() or 0)


async def delete_older_than(db: AsyncSession, cutoff: datetime) -> None:
    """Supprime les instantanés antérieurs à une date."""
    await db.execute(delete(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_date < cutoff))
