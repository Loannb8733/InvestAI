"""Revenus passifs : récompenses de staking et airdrops, par type, par actif et par mois."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.insights.periods import covered_months

_TOP_ASSETS = 10
_HISTORY_SIZE = 30
_PROJECTION_MONTHS = 3

EMPTY_INCOME: dict[str, Any] = {
    "total_income": 0,
    "avg_monthly": 0,
    "projected_annual": 0,
    "by_type": {},
    "by_asset": {},
    "by_month": {},
    "nb_events": 0,
    "history": [],
}


def _rounded_by_amount(amounts: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 2) for key, value in sorted(amounts.items(), key=lambda item: -item[1])}


def _projected_monthly(by_month: dict[str, float]) -> float:
    recent = list(by_month.values())[-_PROJECTION_MONTHS:]
    return sum(recent) / len(recent) if recent else 0


async def passive_income(db: AsyncSession, user_id: str, year: int | None = None) -> dict[str, Any]:
    """Revenus de l'utilisateur, éventuellement d'une année, et projection annuelle sur les trois derniers mois."""
    ids = await repository.portfolio_ids(db, user_id)
    assets = await repository.assets_of_portfolios(db, ids) if ids else {}
    if not assets:
        return {**EMPTY_INCOME}
    transactions = await repository.passive_transactions(db, list(assets), year)
    total = 0.0
    by_type: dict[str, float] = {}
    by_asset: dict[str, float] = {}
    by_month: dict[str, float] = {}
    history = []
    for tx in transactions:
        value = float(tx.quantity * tx.price) if tx.price else 0
        asset = assets.get(str(tx.asset_id))
        symbol = asset.symbol if asset else "?"
        kind = tx.transaction_type.value
        month = tx.executed_at.strftime("%Y-%m") if tx.executed_at else "?"
        total += value
        by_type[kind] = by_type.get(kind, 0) + value
        by_asset[symbol] = by_asset.get(symbol, 0) + value
        by_month[month] = by_month.get(month, 0) + value
        history.append(
            {
                "date": tx.executed_at.isoformat() if tx.executed_at else None,
                "symbol": symbol,
                "type": kind,
                "quantity": round(float(tx.quantity), 8),
                "price": round(float(tx.price), 4) if tx.price else 0,
                "value": round(value, 2),
            }
        )
    months = dict(sorted(by_month.items()))
    return {
        "total_income": round(total, 2),
        "avg_monthly": round(total / covered_months(list(by_month)), 2),
        "projected_annual": round(_projected_monthly(months) * 12, 2),
        "by_type": _rounded_by_amount(by_type),
        "by_asset": dict(list(_rounded_by_amount(by_asset).items())[:_TOP_ASSETS]),
        "by_month": {key: round(value, 2) for key, value in months.items()},
        "nb_events": len(transactions),
        "history": history[:_HISTORY_SIZE],
    }
