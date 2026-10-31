"""Positions en moins-value latente, candidates à une cession pour réduire l'impôt."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset

_FLAT_TAX = 0.30


async def _opportunity(asset: Asset) -> dict[str, Any] | None:
    quantity = float(asset.quantity)
    average = float(asset.avg_buy_price)
    if quantity <= 0 or average <= 0:
        return None
    quote = await price_feed.quote(asset.symbol, asset.asset_type)
    price = float(quote.price) if quote is not None else average
    cost = quantity * average
    value = quantity * price
    unrealized = value - cost
    if unrealized >= 0:
        return None
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type.value,
        "quantity": round(quantity, 8),
        "avg_buy_price": round(average, 2),
        "current_price": round(price, 2),
        "cost_basis": round(cost, 2),
        "current_value": round(value, 2),
        "unrealized_loss": round(unrealized, 2),
        "unrealized_loss_pct": round(unrealized / cost * 100 if cost > 0 else 0, 2),
        "potential_tax_saving": round(abs(unrealized) * _FLAT_TAX, 2),
        "raw_loss": unrealized,
    }


async def tax_loss_opportunities(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """Moins-values latentes, la plus forte en tête, et l'impôt qu'elles pourraient éviter."""
    ids = await repository.portfolio_ids(db, user_id)
    if not ids:
        return {"opportunities": [], "total_harvestable": 0, "estimated_tax_saving": 0}
    opportunities = []
    harvestable = 0.0
    for asset in await repository.held_assets(db, ids):
        opportunity = await _opportunity(asset)
        if opportunity is not None:
            harvestable += opportunity.pop("raw_loss")
            opportunities.append(opportunity)
    opportunities.sort(key=lambda entry: entry["unrealized_loss"])
    return {
        "opportunities": opportunities,
        "total_harvestable": round(harvestable, 2),
        "estimated_tax_saving": round(abs(harvestable) * _FLAT_TAX if harvestable < 0 else 0, 2),
        "nb_candidates": len(opportunities),
        "note": (
            "Vendre ces positions cristallise les moins-values, réduisant l'impôt sur les plus-values. "
            "Attention au wash sale — ne rachetez pas immédiatement le même actif."
        ),
    }
