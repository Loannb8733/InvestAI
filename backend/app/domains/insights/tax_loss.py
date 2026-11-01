"""Positions en moins-value latente, et l'impôt qu'elles peuvent réduire sur les plus-values de l'année."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.service import metrics_service
from app.domains.insights import repository

_FLAT_TAX = 0.30
_NOTE = (
    "Vendre ces positions cristallise les moins-values. Elles ne réduisent l'impôt que sur des plus-values "
    "imposables : sur les cryptomonnaies, uniquement celles de la même année."
)


def _tax_saving(loss: float, gains: float) -> float:
    return round(min(abs(loss), max(gains, 0.0)) * _FLAT_TAX, 2)


def _opportunity(position: dict[str, Any], gains: float) -> dict[str, Any]:
    cost = position["total_invested"]
    loss = position["gain_loss"]
    return {
        "symbol": position["symbol"],
        "name": position["name"],
        "asset_type": position["asset_type"],
        "quantity": round(position["quantity"], 8),
        "avg_buy_price": round(position["avg_buy_price"], 2),
        "current_price": round(position["current_price"] or 0, 2),
        "cost_basis": round(cost, 2),
        "current_value": round(position["current_value"], 2),
        "unrealized_loss": round(loss, 2),
        "unrealized_loss_pct": round(loss / cost * 100 if cost > 0 else 0, 2),
        "potential_tax_saving": _tax_saving(loss, gains),
    }


async def _positions_and_gains(db: AsyncSession, ids: list[Any]) -> tuple[list[dict[str, Any]], float]:
    year = str(datetime.now(UTC).year)
    positions: list[dict[str, Any]] = []
    gains = 0.0
    for portfolio_id in ids:
        metrics = await metrics_service.get_portfolio_metrics(db, str(portfolio_id))
        history = await metrics_service.get_portfolio_history(db, str(portfolio_id))
        positions.extend(metrics["assets"])
        gains += history["realized_by_year"].get(year, 0.0)
    return positions, gains


async def tax_loss_opportunities(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """Moins-values au coût FIFO, la plus forte en tête ; l'économie est plafonnée par les plus-values de l'année."""
    ids = await repository.portfolio_ids(db, user_id)
    positions, gains = await _positions_and_gains(db, ids)
    losers = [position for position in positions if position["gain_loss"] < 0]
    opportunities = sorted((_opportunity(position, gains) for position in losers), key=lambda e: e["unrealized_loss"])
    harvestable = sum(position["gain_loss"] for position in losers)
    return {
        "opportunities": opportunities,
        "total_harvestable": round(harvestable, 2),
        "estimated_tax_saving": _tax_saving(harvestable, gains),
        "realized_gains_this_year": round(gains, 2),
        "nb_candidates": len(opportunities),
        "note": _NOTE,
    }
