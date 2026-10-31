"""Rejeu des transactions jour par jour : quantités détenues, capital investi et capital net."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, NamedTuple

from app.domains.transactions.models import TransactionType

_MIN_QUANTITY = 1e-10
_OUTFLOW_LAST = {TransactionType.SELL, TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT}
_ACCUMULATING = {
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.CONVERSION_IN,
}
_NEUTRAL_OUTFLOWS = {TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT}
_CAPITAL_IN = {TransactionType.BUY, TransactionType.TRANSFER_IN}


class DailyHoldings(NamedTuple):
    """Par date : quantités par symbole, investi cumulé, capital net ; et le type d'actif de chaque symbole."""

    holdings: dict[str, dict[str, float]]
    invested: dict[str, float]
    net_capital: dict[str, float]
    asset_types: dict[str, str]


@dataclass
class _Book:
    holdings: dict[str, float] = field(default_factory=dict)
    invested: float = 0.0
    net_capital: float = 0.0

    def add(self, symbol: str, quantity: float) -> None:
        self.holdings[symbol] = self.holdings.get(symbol, 0.0) + quantity

    def remove(self, symbol: str, quantity: float) -> None:
        self.holdings[symbol] = max(0.0, self.holdings.get(symbol, 0.0) - quantity)

    def apply(self, tx: Any) -> None:
        symbol = tx.symbol.upper()
        quantity = float(tx.quantity)
        rate = getattr(tx, "conversion_rate", None)
        amount = quantity * float(tx.price) * (float(rate) if rate else 1.0)
        kind = tx.transaction_type
        if kind in _CAPITAL_IN:
            self.add(symbol, quantity)
            self.invested += amount
            self.net_capital += amount
        elif kind in _ACCUMULATING:
            self.add(symbol, quantity)
        elif kind == TransactionType.SELL:
            self.remove(symbol, quantity)
            self.net_capital -= amount
        elif kind in _NEUTRAL_OUTFLOWS:
            self.remove(symbol, quantity)


def _day_of(tx: Any) -> str | None:
    moment = tx.executed_at or tx.created_at
    return moment.strftime("%Y-%m-%d") if moment is not None else None


def _asset_type(tx: Any) -> str:
    kind = tx.asset_type
    return kind.value if hasattr(kind, "value") else str(kind)


def replay_daily_holdings(transactions: Sequence[Any], start: datetime, end: datetime) -> DailyHoldings:
    """Rejoue l'historique de `start` à `end` ; le même jour, entrées avant sorties pour ne pas tronquer à zéro."""
    by_day: dict[str, list[Any]] = {}
    asset_types: dict[str, str] = {}
    for tx in transactions:
        day = _day_of(tx)
        if day is None:
            continue
        by_day.setdefault(day, []).append(tx)
        asset_types.setdefault(tx.symbol.upper(), _asset_type(tx))
    book = _Book()
    daily = DailyHoldings({}, {}, {}, asset_types)
    current = start
    while current <= end:
        day = current.strftime("%Y-%m-%d")
        for tx in sorted(by_day.get(day, []), key=lambda t: t.transaction_type in _OUTFLOW_LAST):
            book.apply(tx)
        daily.holdings[day] = {s: q for s, q in book.holdings.items() if q > _MIN_QUANTITY}
        daily.invested[day] = book.invested
        daily.net_capital[day] = book.net_capital
        current += timedelta(days=1)
    return daily
