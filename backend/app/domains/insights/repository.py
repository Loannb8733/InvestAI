"""Requêtes des analyses de frais, de moins-values et de revenus."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, Portfolio
from app.domains.transactions.models import Transaction, TransactionType

_PASSIVE_TYPES = (TransactionType.STAKING_REWARD, TransactionType.AIRDROP)


async def portfolio_ids(db: AsyncSession, user_id: str) -> list[UUID]:
    """Identifiants des portefeuilles de l'utilisateur."""
    result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == user_id))
    return list(result.scalars().all())


async def assets_of_portfolios(db: AsyncSession, ids: list[UUID]) -> dict[str, Asset]:
    """Tous les actifs de ces portefeuilles, par identifiant."""
    result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(ids)))
    return {str(asset.id): asset for asset in result.scalars().all()}


async def held_assets(db: AsyncSession, ids: list[UUID]) -> Sequence[Asset]:
    """Actifs détenus de ces portefeuilles."""
    result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(ids), Asset.quantity > 0))
    return result.scalars().all()


async def transactions_with_fee(db: AsyncSession, asset_ids: list[Any]) -> Sequence[Transaction]:
    """Transactions portant des frais, la plus récente en tête."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.asset_id.in_(asset_ids), Transaction.fee > 0)
        .order_by(Transaction.executed_at.desc())
    )
    return result.scalars().all()


async def passive_transactions(db: AsyncSession, asset_ids: list[Any], year: int | None) -> Sequence[Transaction]:
    """Récompenses et airdrops, éventuellement d'une seule année, le plus récent en tête."""
    query = select(Transaction).where(
        Transaction.asset_id.in_(asset_ids), Transaction.transaction_type.in_(_PASSIVE_TYPES)
    )
    if year:
        query = query.where(extract("year", Transaction.executed_at) == year)
    result = await db.execute(query.order_by(Transaction.executed_at.desc()))
    return result.scalars().all()
