"""Requêtes des métriques."""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction, TransactionType


async def user_portfolios(db: AsyncSession, user_id: str) -> Sequence[Portfolio]:
    """Portefeuilles d'un utilisateur."""
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    return result.scalars().all()


async def portfolio_assets(db: AsyncSession, portfolio_id: Any, *, include_zero: bool = True) -> Sequence[Asset]:
    """Actifs d'un portefeuille, avec ou sans ceux à quantité nulle."""
    query = select(Asset).where(Asset.portfolio_id == portfolio_id)
    if not include_zero:
        query = query.where(Asset.quantity > 0)
    return (await db.execute(query)).scalars().all()


async def first_transaction_dates(db: AsyncSession, asset_ids: list[Any]) -> dict[str, datetime]:
    """Date de la première transaction de chaque actif."""
    result = await db.execute(
        select(Transaction.asset_id, func.min(Transaction.executed_at))
        .where(Transaction.asset_id.in_(asset_ids))
        .group_by(Transaction.asset_id)
    )
    return {str(asset_id): first for asset_id, first in result.all() if first}


async def fees_by_asset(db: AsyncSession, asset_ids: list[Any]) -> dict[str, float]:
    """Frais cumulés par actif ; une transaction de frais vaut quantité fois prix."""
    amount = case(
        (Transaction.transaction_type == TransactionType.FEE, Transaction.quantity * Transaction.price),
        else_=func.coalesce(Transaction.fee, 0),
    )
    result = await db.execute(
        select(Transaction.asset_id, func.sum(amount))
        .where(Transaction.asset_id.in_(asset_ids))
        .group_by(Transaction.asset_id)
    )
    return {str(asset_id): float(total or 0) for asset_id, total in result.all()}


async def portfolio_transactions(db: AsyncSession, portfolio_id: Any) -> Sequence[Transaction]:
    """Toutes les transactions d'un portefeuille, y compris celles d'actifs soldés."""
    result = await db.execute(
        select(Transaction)
        .join(Asset, Transaction.asset_id == Asset.id)
        .where(Asset.portfolio_id == portfolio_id)
        .order_by(Transaction.executed_at, Transaction.id)
    )
    return result.scalars().all()


async def priced_history(db: AsyncSession, symbols: list[str], cutoff: date) -> list[tuple[str, float]]:
    """Cours quotidiens depuis `cutoff`, par symbole puis par date."""
    result = await db.execute(
        select(AssetPriceHistory.symbol, AssetPriceHistory.price_eur)
        .where(AssetPriceHistory.symbol.in_(symbols), AssetPriceHistory.price_date >= cutoff)
        .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
    )
    return [(symbol, float(price)) for symbol, price in result.all()]


async def non_crowdfunding_assets(db: AsyncSession, portfolio_id: Any) -> Sequence[Asset]:
    """Actifs d'un portefeuille hors crowdfunding, géré par son propre domaine."""
    result = await db.execute(
        select(Asset).where(Asset.portfolio_id == portfolio_id, Asset.asset_type != AssetType.CROWDFUNDING)
    )
    return result.scalars().all()


async def transactions_of_assets(db: AsyncSession, asset_ids: list[Any]) -> Sequence[Transaction]:
    """Transactions de ces actifs, la plus récente en tête."""
    result = await db.execute(
        select(Transaction).where(Transaction.asset_id.in_(asset_ids)).order_by(Transaction.executed_at.desc())
    )
    return result.scalars().all()


async def historical_prices(db: AsyncSession, symbols: list[str], dates: list[date]) -> dict[tuple[str, date], Decimal]:
    """Cours de ces symboles aux dates demandées."""
    result = await db.execute(
        select(AssetPriceHistory.symbol, AssetPriceHistory.price_date, AssetPriceHistory.price_eur).where(
            AssetPriceHistory.symbol.in_(symbols), AssetPriceHistory.price_date.in_(dates)
        )
    )
    return {(symbol, day): Decimal(str(price)) for symbol, day, price in result.all()}
