"""Revenus passifs : récompenses, airdrops, dividendes et intérêts, par type, par actif et par mois."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.insights.periods import covered_months
from app.domains.portfolio.models import Asset
from app.domains.transactions.models import Transaction, TransactionType

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
    "nb_sans_cours": 0,
    "history": [],
}


def _rounded_by_amount(amounts: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 2) for key, value in sorted(amounts.items(), key=lambda item: -item[1])}


def _projected_annual(recurring: dict[str, float]) -> float:
    recent = [amount for _, amount in sorted(recurring.items())][-_PROJECTION_MONTHS:]
    return round(sum(recent) / len(recent) * 12, 2) if recent else 0


@dataclass
class _Income:
    total: float = 0.0
    unpriced: int = 0
    by_type: dict[str, float] = field(default_factory=dict)
    by_asset: dict[str, float] = field(default_factory=dict)
    by_month: dict[str, float] = field(default_factory=dict)
    recurring_by_month: dict[str, float] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def add(self, tx: Transaction, symbol: str) -> None:
        rate = float(tx.conversion_rate) if tx.conversion_rate else 1.0
        value = float(tx.quantity * tx.price) * rate if tx.price else 0.0
        kind = tx.transaction_type.value
        month = tx.executed_at.strftime("%Y-%m") if tx.executed_at else "?"
        if value > 0:
            self.total += value
            self.by_type[kind] = self.by_type.get(kind, 0) + value
            self.by_asset[symbol] = self.by_asset.get(symbol, 0) + value
            self.by_month[month] = self.by_month.get(month, 0) + value
            if tx.transaction_type != TransactionType.AIRDROP:
                self.recurring_by_month[month] = self.recurring_by_month.get(month, 0) + value
        else:
            self.unpriced += 1
        self.history.append(
            {
                "date": tx.executed_at.isoformat() if tx.executed_at else None,
                "symbol": symbol,
                "type": kind,
                "quantity": round(float(tx.quantity), 8),
                "price": round(float(tx.price), 4) if tx.price else 0,
                "value": round(value, 2),
            }
        )


def _symbol(assets: dict[str, Asset], tx: Transaction) -> str:
    asset = assets.get(str(tx.asset_id))
    return asset.symbol if asset else "?"


async def passive_income(db: AsyncSession, user_id: str, year: int | None = None) -> dict[str, Any]:
    """Revenus de l'utilisateur ; projection sur les trois derniers mois de revenus récurrents, airdrops exclus."""
    ids = await repository.portfolio_ids(db, user_id)
    assets = await repository.assets_of_portfolios(db, ids) if ids else {}
    if not assets:
        return {**EMPTY_INCOME}
    transactions = await repository.passive_transactions(db, list(assets), year)
    income = _Income()
    for tx in transactions:
        income.add(tx, _symbol(assets, tx))
    return {
        "total_income": round(income.total, 2),
        "avg_monthly": round(income.total / covered_months(list(income.by_month)), 2),
        "projected_annual": _projected_annual(income.recurring_by_month),
        "by_type": _rounded_by_amount(income.by_type),
        "by_asset": dict(list(_rounded_by_amount(income.by_asset).items())[:_TOP_ASSETS]),
        "by_month": {key: round(value, 2) for key, value in sorted(income.by_month.items())},
        "nb_events": len(transactions),
        "nb_sans_cours": income.unpriced,
        "history": income.history[:_HISTORY_SIZE],
    }
