import logging

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType
from app.domains.transactions.models import Transaction, TransactionType

logger = logging.getLogger(__name__)

QUOTED_TYPES = (AssetType.CRYPTO, AssetType.STOCK, AssetType.ETF)


async def asset_price(asset: Asset) -> float:
    """Cours courant d'un actif coté, 0 s'il est indisponible ; le prix de revient pour un actif non coté.

    Le zéro signale l'absence de cours à l'appelant : rendre le prix de revient ferait comparer celui-ci à
    lui-même, ou déclencher une alerte de baisse sur un actif qui n'a pas bougé.
    """
    quoted = asset.asset_type in QUOTED_TYPES
    try:
        if quoted:
            quote = await price_feed.quote(asset.symbol, asset.asset_type)
            return float(quote.price) if quote is not None else 0.0
        return float(asset.avg_buy_price)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cours indisponible pour %s (%s) : %s — alerte non évaluée", asset.symbol, asset.asset_type, exc)
        return 0.0 if quoted else float(asset.avg_buy_price)


async def daily_change(asset: Asset) -> float | None:
    """Variation sur 24 h en pourcentage, None si le cours manque."""
    try:
        quote = await price_feed.quote(asset.symbol, asset.asset_type)
        if quote is not None:
            return quote.change_percent_24h
    except Exception as exc:  # noqa: BLE001
        logger.debug("24h change fetch failed for %s: %s", asset.symbol, exc)
    return None


async def breakeven_price(db: AsyncSession, asset: Asset) -> float | None:
    """Prix de rentabilité : investi au prix moyen plus tous les frais de l'actif, rapporté à la quantité."""
    quantity = float(asset.quantity)
    if quantity <= 0:
        return None
    fees = case(
        (Transaction.transaction_type == TransactionType.FEE, Transaction.quantity * Transaction.price),
        else_=func.coalesce(Transaction.fee, 0),
    )
    row = (await db.execute(select(func.sum(fees).label("total_fees")).where(Transaction.asset_id == asset.id))).one()
    return (quantity * float(asset.avg_buy_price) + float(row[0] or 0)) / quantity
