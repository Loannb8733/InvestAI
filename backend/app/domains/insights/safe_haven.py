"""Part du patrimoine en valeurs refuges."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.classification import is_safe_haven

logger = logging.getLogger(__name__)


async def gold_exposure(db: AsyncSession, user_id: str, total_value: float) -> float:
    """Fraction du patrimoine en or ; une ligne sans cours n'y compte pas."""
    ids = await repository.portfolio_ids(db, user_id)
    if not ids:
        return 0.0
    gold_value = 0.0
    for asset in await repository.held_assets(db, ids):
        if not is_safe_haven(asset.symbol):
            continue
        try:
            quote = await price_feed.quote(asset.symbol, asset.asset_type)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Safe-haven price fetch failed for %s: %s", asset.symbol, exc)
            continue
        if quote is not None:
            gold_value += float(asset.quantity) * float(quote.price)
    return gold_value / total_value if total_value > 0 else 0.0
