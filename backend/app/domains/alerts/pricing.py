import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType
from app.domains.transactions.models import Transaction, TransactionType

logger = logging.getLogger(__name__)

QUOTED_TYPES = (AssetType.CRYPTO, AssetType.STOCK, AssetType.ETF)


async def asset_price(asset: Asset, currency: str = "EUR") -> float:
    """Cours d'un actif coté dans ``currency``, 0 s'il est indisponible ; le prix de revient d'un actif non coté.

    Le zéro signale l'absence de cours à l'appelant : rendre le prix de revient ferait comparer celui-ci à
    lui-même, ou déclencher une alerte de baisse sur un actif qui n'a pas bougé. Un actif non coté n'a de
    prix qu'en euros.
    """
    quoted = asset.asset_type in QUOTED_TYPES
    try:
        if quoted:
            quote = await price_feed.quote(asset.symbol, asset.asset_type, currency)
            return float(quote.price) if quote is not None else 0.0
        return float(asset.avg_buy_price) if currency == "EUR" else 0.0
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
    """Prix de rentabilité : prix moyen d'achat, qui contient déjà les frais d'achat, plus les frais saisis à part.

    Les frais saisis à part sont les transactions FEE, rapportées à la quantité détenue.
    """
    quantity = float(asset.quantity)
    if quantity <= 0:
        return None
    standalone = select(func.sum(Transaction.quantity * Transaction.price)).where(
        Transaction.asset_id == asset.id, Transaction.transaction_type == TransactionType.FEE
    )
    fees = float((await db.execute(standalone)).scalar() or 0)
    return (quantity * float(asset.avg_buy_price) + fees) / quantity
