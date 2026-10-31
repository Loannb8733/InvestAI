"""Rejeu FIFO unique, partagé par l'affichage et la fiscalité.

Il ne lit pas la base et ne calcule aucun gain : les appelants fournissent les transactions et
appliquent leur formule à partir des événements émis.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.transactions.cost_basis.acquisitions import (
    TRANSIT_PREFIX,
    apply_buy,
    apply_dividend,
    apply_reward,
    apply_sell,
    apply_transfer_in,
    apply_transfer_out,
)
from app.domains.transactions.cost_basis.config import ReplayConfig, ReplayEvent, ReplayResult
from app.domains.transactions.cost_basis.context import ReplayContext, ReplayRow, aware
from app.domains.transactions.cost_basis.conversions import apply_conversion_in, apply_conversion_out
from app.domains.transactions.models import TransactionType

_EPOCH = datetime.min.replace(tzinfo=UTC)

_STEPS: dict[TransactionType, Callable[[ReplayContext, ReplayRow], None]] = {
    TransactionType.BUY: apply_buy,
    TransactionType.SELL: apply_sell,
    TransactionType.AIRDROP: apply_reward,
    TransactionType.STAKING_REWARD: apply_reward,
    TransactionType.TRANSFER_OUT: apply_transfer_out,
    TransactionType.TRANSFER_IN: apply_transfer_in,
    TransactionType.CONVERSION_OUT: apply_conversion_out,
    TransactionType.CONVERSION_IN: apply_conversion_in,
    TransactionType.DIVIDEND: apply_dividend,
}


def _replay_order(tx: Any) -> tuple[datetime, int, str]:
    moment = tx.executed_at or _EPOCH
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment, 0 if tx.transaction_type == TransactionType.TRANSFER_OUT else 1, str(tx.id)


def sort_transactions(transactions: list[Any]) -> list[Any]:
    """Ordre canonique : date, transfert sortant avant l'entrant de même date, puis identifiant."""
    return sorted(transactions, key=_replay_order)


def _row(tx: Any, symbol: str) -> ReplayRow:
    exchange = (tx.exchange or "").strip()
    return ReplayRow(
        tx=tx,
        symbol=symbol,
        exchange=exchange,
        key=(symbol, exchange),
        quantity=Decimal(str(tx.quantity)),
        executed_at=aware(tx.executed_at),
    )


def replay(
    transactions: list[Any],
    aid_to_symbol: dict[str, str],
    config: ReplayConfig,
    *,
    aid_to_avg_price: dict[str, Decimal] | None = None,
    sym_avg_price: dict[str, Decimal] | None = None,
    usd_to_portfolio: Decimal | float | None = None,
    on_event: Callable[[ReplayEvent], None] | None = None,
) -> ReplayResult:
    """Rejoue `transactions` dans l'ordre donné ; un actif absent de `aid_to_symbol` est hors périmètre."""
    ctx = ReplayContext(
        config=config,
        result=ReplayResult(),
        aid_to_symbol=aid_to_symbol,
        aid_to_avg_price=aid_to_avg_price or {},
        sym_avg_price=sym_avg_price or {},
        usd_to_portfolio=usd_to_portfolio,
        conversion_ins=[tx for tx in transactions if tx.transaction_type == TransactionType.CONVERSION_IN],
        on_event=on_event,
    )
    for tx in transactions:
        symbol = aid_to_symbol.get(str(tx.asset_id))
        if symbol is None or (config.skip_null_executed_at and not tx.executed_at):
            continue
        step = _STEPS.get(tx.transaction_type)
        if step is not None:
            step(ctx, _row(tx, symbol))
    fifo = ctx.result.fifo
    for key in [key for key in fifo if key[1].startswith(TRANSIT_PREFIX)]:
        ctx.result.orphan_transit[key] = fifo.pop(key)
    return ctx.result
