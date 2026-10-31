"""PRU en coût moyen pondéré, frais compris, calculé depuis le journal des transactions."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domains.transactions.cost_basis.context import ONE
from app.domains.transactions.cost_basis.layers import ZERO, FifoKey
from app.domains.transactions.models import TransactionType


@dataclass
class _Position:
    cost: Decimal = ZERO
    buy_qty: Decimal = ZERO
    current_qty: Decimal = ZERO
    pru: Decimal = ZERO
    needs_reset: bool = False

    def refresh_pru(self) -> None:
        if self.buy_qty > ZERO:
            self.pru = self.cost / self.buy_qty

    def reduce(self, quantity: Decimal) -> None:
        self.current_qty = max(ZERO, self.current_qty - quantity)


def _apply_buy(position: _Position, qty: Decimal, price: Decimal, fee: Decimal) -> None:
    if position.needs_reset:
        position.cost = ZERO
        position.buy_qty = ZERO
        position.needs_reset = False
    position.cost += qty * price + fee
    position.buy_qty += qty
    position.current_qty += qty
    position.refresh_pru()


def _apply_sell(position: _Position, qty: Decimal, _price: Decimal, _fee: Decimal) -> None:
    position.reduce(qty)
    if position.current_qty <= ZERO:
        position.needs_reset = True


def _apply_transfer_in(position: _Position, qty: Decimal, price: Decimal, fee: Decimal) -> None:
    if price > ZERO:
        position.cost += qty * price + fee
        position.buy_qty += qty
    elif position.pru > ZERO:
        position.cost += qty * position.pru
        position.buy_qty += qty
    position.refresh_pru()
    position.current_qty += qty


def _apply_outflow(position: _Position, qty: Decimal, _price: Decimal, _fee: Decimal) -> None:
    position.reduce(qty)


def _apply_reward(position: _Position, qty: Decimal, _price: Decimal, _fee: Decimal) -> None:
    position.current_qty += qty


def _apply_conversion_in(position: _Position, qty: Decimal, price: Decimal, _fee: Decimal) -> None:
    if price > ZERO:
        position.cost += qty * price
        position.buy_qty += qty
        position.refresh_pru()
    position.current_qty += qty


_STEPS: dict[TransactionType, Callable[[_Position, Decimal, Decimal, Decimal], None]] = {
    TransactionType.BUY: _apply_buy,
    TransactionType.SELL: _apply_sell,
    TransactionType.TRANSFER_IN: _apply_transfer_in,
    TransactionType.TRANSFER_OUT: _apply_outflow,
    TransactionType.CONVERSION_OUT: _apply_outflow,
    TransactionType.STAKING_REWARD: _apply_reward,
    TransactionType.AIRDROP: _apply_reward,
    TransactionType.CONVERSION_IN: _apply_conversion_in,
}


def compute_cump_pru(
    transactions: list[Any],
    aid_to_symbol: dict[str, str],
    aid_to_exchange: dict[str, str],
) -> dict[FifoKey, Decimal]:
    """PRU par (symbole, plateforme) : une vente ne le change pas, un achat après une position soldée repart à zéro."""
    positions: dict[FifoKey, _Position] = {}
    for tx in transactions:
        asset_id = str(tx.asset_id)
        symbol = aid_to_symbol.get(asset_id, "")
        if not symbol:
            continue
        position = positions.setdefault((symbol, aid_to_exchange.get(asset_id, "")), _Position())
        rate = Decimal(str(tx.conversion_rate)) if getattr(tx, "conversion_rate", None) else ONE
        step = _STEPS.get(tx.transaction_type)
        if step is not None:
            step(
                position,
                Decimal(str(tx.quantity or 0)),
                Decimal(str(tx.price or 0)) * rate,
                Decimal(str(tx.fee or 0)) * rate,
            )
    return {
        key: position.pru for key, position in positions.items() if position.pru > ZERO and not position.needs_reset
    }
