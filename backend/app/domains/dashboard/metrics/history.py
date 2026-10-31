"""Historique d'investissement d'un portefeuille, actifs soldés compris."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics import repository
from app.domains.dashboard.metrics.ledger import replay_assets
from app.domains.portfolio.classification import is_cash_like
from app.domains.portfolio.models import Asset
from app.domains.transactions.cost_basis.config import ReplayEvent
from app.domains.transactions.cost_basis.context import ONE
from app.domains.transactions.cost_basis.layers import ZERO
from app.domains.transactions.models import Transaction, TransactionType

_INFLOWS = {
    TransactionType.BUY,
    TransactionType.TRANSFER_IN,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.CONVERSION_IN,
    TransactionType.INTEREST,
}
_DISPOSALS = {TransactionType.SELL, TransactionType.CONVERSION_OUT}
_MIN_REMAINING_VALUE = 0.10

EMPTY_HISTORY: dict[str, Any] = {
    "total_invested_all_time": 0.0,
    "total_sold": 0.0,
    "total_fees": 0.0,
    "realized_gains": 0.0,
    "current_holdings_count": 0,
    "sold_assets_count": 0,
    "sold_assets": [],
}


@dataclass
class _AssetHistory:
    asset: Asset
    bought: Decimal = ZERO
    bought_value: Decimal = ZERO
    bought_fiat_value: Decimal = ZERO
    sold: Decimal = ZERO
    sold_value: Decimal = ZERO
    sold_fiat_value: Decimal = ZERO
    fees: Decimal = ZERO
    realized: Decimal = ZERO
    first: datetime | None = None
    last: datetime | None = None

    def touch(self, moment: datetime | None) -> None:
        if moment is None:
            return
        if self.last is None or moment > self.last:
            self.last = moment
        if self.first is None or moment < self.first:
            self.first = moment

    def is_mostly_sold(self) -> bool:
        quantity = float(self.asset.quantity)
        remaining = quantity
        if self.bought > 0 and self.bought_value > 0:
            remaining = quantity * float(self.bought_value / self.bought)
        return remaining < _MIN_REMAINING_VALUE

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.asset.id),
            "symbol": self.asset.symbol,
            "name": self.asset.name,
            "asset_type": self.asset.asset_type.value,
            "exchange": self.asset.exchange,
            "current_quantity": float(self.asset.quantity),
            "total_bought": float(self.bought),
            "total_bought_value": float(self.bought_fiat_value),
            "total_sold": float(self.sold),
            "total_sold_value": float(self.sold_value),
            "total_fees": float(self.fees),
            "realized_gain": float(self.realized),
            "first_transaction": self.first.isoformat() if self.first else None,
            "last_transaction": self.last.isoformat() if self.last else None,
        }


@dataclass(frozen=True)
class _Prices:
    historical: dict[tuple[str, date], Decimal]

    def resolve(self, tx: Transaction, symbol: str) -> Decimal:
        price = Decimal(str(tx.price))
        if price > 0:
            return price * (Decimal(str(tx.conversion_rate)) if tx.conversion_rate else ONE)
        if tx.executed_at is not None:
            return self.historical.get((symbol, tx.executed_at.date())) or ZERO
        return ZERO


def _record_fee(history: _AssetHistory, tx: Transaction) -> None:
    if tx.transaction_type == TransactionType.FEE:
        history.fees += Decimal(str(tx.quantity)) * Decimal(str(tx.price))
    else:
        history.fees += Decimal(str(tx.fee or 0))


def _record_inflow(history: _AssetHistory, tx: Transaction, price: Decimal) -> None:
    quantity = Decimal(str(tx.quantity))
    history.bought += quantity
    history.bought_value += quantity * price
    stored_price = Decimal(str(tx.price))
    if tx.transaction_type == TransactionType.BUY and stored_price > 0:
        rate = Decimal(str(tx.conversion_rate)) if tx.conversion_rate else ONE
        history.bought_fiat_value += quantity * stored_price * rate


def _record_disposal(history: _AssetHistory, tx: Transaction, price: Decimal) -> None:
    quantity = Decimal(str(tx.quantity))
    history.sold += quantity
    history.sold_value += quantity * price
    if tx.transaction_type == TransactionType.SELL:
        history.sold_fiat_value += quantity * price


async def _load_prices(db: AsyncSession, transactions: list[Transaction], symbols: dict[str, str]) -> _Prices:
    needed = {
        (symbols[str(tx.asset_id)], tx.executed_at.date())
        for tx in transactions
        if Decimal(str(tx.price)) == 0 and tx.executed_at is not None and str(tx.asset_id) in symbols
    }
    if not needed:
        return _Prices({})
    found = await repository.historical_prices(db, list({s for s, _ in needed}), list({d for _, d in needed}))
    return _Prices(found)


def _replay(transactions: list[Transaction], histories: dict[str, _AssetHistory], prices: _Prices) -> None:
    for tx in transactions:
        history = histories.get(str(tx.asset_id))
        if history is None:
            continue
        symbol = history.asset.symbol.upper()
        history.touch(tx.executed_at)
        _record_fee(history, tx)
        if tx.transaction_type in _INFLOWS:
            _record_inflow(history, tx, prices.resolve(tx, symbol))
        elif tx.transaction_type in _DISPOSALS:
            _record_disposal(history, tx, prices.resolve(tx, symbol))


def _realize(event: ReplayEvent, histories: dict[str, _AssetHistory], prices: _Prices) -> None:
    history = histories[str(event.tx.asset_id)]
    if event.kind == "SELL":
        proceeds = event.quantity * prices.resolve(event.tx, event.symbol) - event.fee
        history.realized += proceeds - event.cost_removed
    elif event.kind == "CONVERSION_OUT" and event.matched:
        history.realized += event.dest_layer_cost - event.cost_removed


def _summarize(histories: dict[str, _AssetHistory]) -> dict[str, Any]:
    invested = sold = sold_fiat = fees = ZERO
    holdings: list[dict[str, Any]] = []
    sold_assets: list[dict[str, Any]] = []
    for history in histories.values():
        if is_cash_like(history.asset.symbol):
            continue
        invested += history.bought_fiat_value
        sold += history.sold_value
        sold_fiat += history.sold_fiat_value
        fees += history.fees
        if float(history.asset.quantity) <= 0:
            if history.sold > 0:
                sold_assets.append(history.as_dict())
        elif history.sold > 0 and history.is_mostly_sold():
            sold_assets.append(history.as_dict())
        else:
            holdings.append(history.as_dict())
    sold_assets.sort(key=lambda entry: entry["total_bought_value"], reverse=True)
    realized = sum((Decimal(str(entry["realized_gain"])) for entry in holdings + sold_assets), ZERO)
    return {
        "total_invested_all_time": float(invested),
        "total_sold": float(sold),
        "total_sold_fiat": float(sold_fiat),
        "total_fees": float(fees),
        "realized_gains": float(realized),
        "current_holdings_count": len(holdings),
        "sold_assets_count": len(sold_assets),
        "sold_assets": sold_assets,
    }


async def compute_portfolio_history(db: AsyncSession, portfolio_id: str, currency: str = "EUR") -> dict[str, Any]:
    """Montants investis et vendus, frais et gains réalisés au coût FIFO, hors crowdfunding et liquidités."""
    assets = await repository.non_crowdfunding_assets(db, portfolio_id)
    if not assets:
        return {**EMPTY_HISTORY, "sold_assets": []}
    transactions = list(await repository.transactions_of_assets(db, [asset.id for asset in assets]))
    histories = {str(asset.id): _AssetHistory(asset) for asset in assets}
    symbols = {str(asset.id): asset.symbol.upper() for asset in assets}
    prices = await _load_prices(db, transactions, symbols)
    _replay(transactions, histories, prices)
    replay_assets(transactions, assets, currency, on_event=lambda event: _realize(event, histories, prices))
    return _summarize(histories)
