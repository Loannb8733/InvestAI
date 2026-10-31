"""Requêtes de l'écran du tableau de bord."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.alerts.models import Alert
from app.domains.calendar.models import CalendarEvent
from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType


async def first_transaction_date(db: AsyncSession, user_id: UUID) -> datetime | None:
    """Date de la première transaction de l'utilisateur."""
    result = await db.execute(
        select(func.min(Transaction.executed_at))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
    )
    return result.scalar()


async def net_staked_quantities(db: AsyncSession, user_id: UUID) -> dict[str, float]:
    """Quantité nette en staking par symbole, jamais négative."""
    signed = case(
        (Transaction.transaction_type == TransactionType.STAKING, Transaction.quantity),
        (Transaction.transaction_type == TransactionType.UNSTAKING, -Transaction.quantity),
        else_=0,
    )
    result = await db.execute(
        select(Asset.symbol, func.sum(signed))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(
            Portfolio.user_id == user_id,
            Transaction.transaction_type.in_([TransactionType.STAKING, TransactionType.UNSTAKING]),
        )
        .group_by(Asset.symbol)
    )
    return {symbol.upper(): max(0, float(total)) for symbol, total in result.all()}


async def staking_rewards(db: AsyncSession, user_id: UUID) -> dict[str, float]:
    """Quantité cumulée de récompenses par symbole."""
    result = await db.execute(
        select(Asset.symbol, func.sum(Transaction.quantity))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id, Transaction.transaction_type == TransactionType.STAKING_REWARD)
        .group_by(Asset.symbol)
    )
    return {symbol.upper(): float(total) for symbol, total in result.all()}


async def first_reward_date(db: AsyncSession, user_id: UUID) -> datetime | None:
    """Date de la première récompense de staking."""
    result = await db.execute(
        select(func.min(Transaction.executed_at))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id, Transaction.transaction_type == TransactionType.STAKING_REWARD)
    )
    return result.scalar()


async def asset_currencies(db: AsyncSession, user_id: UUID) -> dict[str, str]:
    """Devise de dénomination de chaque actif, EUR par défaut."""
    result = await db.execute(
        select(Asset.id, Asset.currency)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
    )
    return {str(asset_id): (currency or "EUR").upper() for asset_id, currency in result.all()}


async def user_assets(db: AsyncSession, user_id: UUID) -> Sequence[Asset]:
    """Tous les actifs de l'utilisateur."""
    result = await db.execute(
        select(Asset).join(Portfolio, Asset.portfolio_id == Portfolio.id).where(Portfolio.user_id == user_id)
    )
    return result.scalars().all()


async def latest_transactions(
    db: AsyncSession, asset_ids: list[Any], limit: int, since: datetime | None
) -> Sequence[Transaction]:
    """Dernières transactions ; une ligne sans date d'exécution est située par sa date de création."""
    query = (
        select(Transaction)
        .where(Transaction.asset_id.in_(asset_ids))
        .order_by(func.coalesce(Transaction.executed_at, Transaction.created_at).desc())
        .limit(limit)
    )
    if since is not None:
        query = query.where(Transaction.executed_at >= since)
    return (await db.execute(query)).scalars().all()


async def active_alerts(db: AsyncSession, user_id: UUID, limit: int) -> Sequence[Alert]:
    """Alertes actives de l'utilisateur."""
    result = await db.execute(select(Alert).where(Alert.user_id == user_id, Alert.is_active.is_(True)).limit(limit))
    return result.scalars().all()


async def assets_by_id(db: AsyncSession, asset_ids: list[Any]) -> dict[Any, Asset]:
    """Actifs demandés, par identifiant."""
    result = await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    return {asset.id: asset for asset in result.scalars().all()}


async def upcoming_events(
    db: AsyncSession, user_id: UUID, start: datetime, end: datetime, limit: int
) -> Sequence[CalendarEvent]:
    """Échéances non réalisées sur l'intervalle, la plus proche en tête."""
    result = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_date >= start,
            CalendarEvent.event_date <= end,
            CalendarEvent.is_completed.is_(False),
        )
        .order_by(CalendarEvent.event_date.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def owns_portfolio(db: AsyncSession, portfolio_id: UUID, user_id: UUID) -> bool:
    """Dit si le portefeuille appartient à l'utilisateur."""
    result = await db.execute(select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id))
    return result.scalar_one_or_none() is not None


async def held_symbols(db: AsyncSession, portfolio_id: str) -> Sequence[tuple[str, AssetType]]:
    """Symboles détenus dans un portefeuille, avec leur type."""
    result = await db.execute(
        select(Asset.symbol, Asset.asset_type).where(Asset.portfolio_id == portfolio_id, Asset.quantity > 0).distinct()
    )
    return [(symbol, kind) for symbol, kind in result.all()]


async def has_global_snapshot_since(db: AsyncSession, user_id: str, since: datetime) -> bool:
    """Dit si un instantané du compte existe depuis une date."""
    result = await db.execute(
        select(func.count())
        .select_from(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.snapshot_date >= since,
            PortfolioSnapshot.portfolio_id.is_(None),
        )
    )
    return bool(result.scalar())


async def insert_global_snapshot(
    db: AsyncSession,
    user_id: str,
    moment: datetime,
    value: Decimal,
    invested: Decimal,
    currency: str,
) -> None:
    """Pose l'instantané du compte ; s'il existe déjà pour ce jour, la base le conserve."""
    await db.execute(
        insert(PortfolioSnapshot)
        .values(
            id=uuid4(),
            user_id=user_id,
            portfolio_id=None,
            snapshot_date=moment,
            total_value=value,
            total_invested=invested,
            currency=currency,
        )
        .on_conflict_do_nothing()
    )
