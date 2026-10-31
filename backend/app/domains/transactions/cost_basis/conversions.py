"""Étapes du rejeu pour les conversions crypto vers crypto."""

import logging
from decimal import Decimal

from app.domains.portfolio.classification import STABLECOIN_PEGS, is_stablecoin
from app.domains.transactions.cost_basis.config import (
    ConversionDestBasis,
    FeeHandling,
    ReplayEvent,
    UnmatchedConversionOutPolicy,
)
from app.domains.transactions.cost_basis.context import (
    ONE,
    ReplayContext,
    ReplayRow,
    aware,
    fx_rate,
    transaction_currency,
)
from app.domains.transactions.cost_basis.layers import ZERO, FifoKey, Layer, consume_layers, total_quantity
from app.domains.transactions.cost_basis.matching import ConversionMatch, match_conversion_in

logger = logging.getLogger(__name__)


def conversion_dest_unit_cost(cost_removed: Decimal, matched_qty: Decimal, recorded_price: Decimal) -> Decimal:
    """Coût unitaire de la destination : prix enregistré, ou coût source reporté s'il manque."""
    if matched_qty <= ZERO:
        return ZERO
    if recorded_price > ZERO:
        return recorded_price
    return cost_removed / matched_qty


def _seed_stablecoin_shortfall(ctx: ReplayContext, row: ReplayRow, shortfall: Decimal) -> None:
    if STABLECOIN_PEGS.get(row.symbol) == "EUR":
        unit_cost, currency, rate = ONE, "EUR", ONE
    else:
        unit_cost = Decimal(str(ctx.usd_to_portfolio or 0)) or ONE
        currency, rate = "USD", unit_cost
    ctx.add_layer(
        row.key,
        Layer(
            qty=shortfall,
            unit_cost=unit_cost,
            unit_cost_base=ONE,
            currency=currency,
            fx_rate=rate,
            is_paid=True,
            acquired_at=row.executed_at,
        ),
    )
    logger.info(
        "Seeded synthetic %s layer for stablecoin %s@%s qty=%s unit_cost=%s (tx_id=%s)",
        currency,
        row.symbol,
        row.exchange,
        shortfall,
        unit_cost,
        row.tx.id,
    )


def _prepare_source_pool(ctx: ReplayContext, row: ReplayRow, match: ConversionMatch) -> list[Layer]:
    pool = ctx.result.fifo.get(row.key, [])
    pool_quantity = total_quantity(pool)
    if match.symbol is None or row.quantity <= pool_quantity:
        return pool
    if ctx.config.seed_stablecoin_layers and is_stablecoin(row.symbol):
        _seed_stablecoin_shortfall(ctx, row, row.quantity - pool_quantity)
        return ctx.result.fifo[row.key]
    ctx.warn(
        "Over-conversion: CONVERSION_OUT qty=%s > pool=%s for %s@%s (tx_id=%s)",
        row.quantity,
        pool_quantity,
        row.symbol,
        row.exchange,
        row.tx.id,
    )
    return pool


def _destination_unit_cost(ctx: ReplayContext, cost_removed: Decimal, match: ConversionMatch) -> Decimal:
    if ctx.config.conversion_dest_basis is ConversionDestBasis.RECORDED_PRICE:
        return conversion_dest_unit_cost(cost_removed, match.quantity, match.price)
    return cost_removed / match.quantity


def _add_destination_layer(
    ctx: ReplayContext, row: ReplayRow, match: ConversionMatch, cost_removed: Decimal, rate: Decimal
) -> Decimal:
    if match.symbol is None or match.quantity <= 0:
        return ZERO
    key: FifoKey = (match.symbol, match.exchange or (row.tx.exchange or "").strip())
    paid = cost_removed > 0
    unit_cost = _destination_unit_cost(ctx, cost_removed, match) if paid else ZERO
    ctx.add_layer(
        key,
        Layer(
            qty=match.quantity,
            unit_cost=unit_cost,
            unit_cost_base=(unit_cost / rate if rate else unit_cost) if paid else ZERO,
            currency=transaction_currency(row.tx),
            fx_rate=rate,
            is_paid=paid,
            acquired_at=row.executed_at,
        ),
    )
    return cost_removed if paid else ZERO


def apply_conversion_out(ctx: ReplayContext, row: ReplayRow) -> None:
    """Consomme la source et crée la couche de destination, sauf sortie sans destination à conserver."""
    match = match_conversion_in(ctx, row.tx, row.symbol)
    rate = fx_rate(row.tx)
    price = Decimal(str(row.tx.price or 0)) * rate
    fee = Decimal(str(row.tx.fee or 0)) * rate
    event = ReplayEvent(
        kind="CONVERSION_OUT",
        tx=row.tx,
        tx_dt=row.executed_at,
        symbol=row.symbol,
        quantity=row.quantity,
        price=price,
        fee=fee,
    )
    if match.symbol is None and ctx.config.unmatched_conversion_out is UnmatchedConversionOutPolicy.PRESERVE:
        ctx.warn(
            "Unmatched CONVERSION_OUT: tx_id=%s src=%s qty=%s exchange=%s notes='%s' — cost preserved on source",
            row.tx.id,
            row.symbol,
            row.quantity,
            row.exchange,
            row.tx.notes or "",
        )
        ctx.emit(event)
        return
    cost_removed, oldest = consume_layers(_prepare_source_pool(ctx, row, match), row.quantity)
    event.cost_removed = cost_removed
    event.oldest_acquired_at = aware(oldest)
    event.dest_cost = _add_destination_layer(ctx, row, match, cost_removed, rate)
    event.matched = match.symbol is not None
    event.dest_symbol = match.symbol
    event.dest_qty = match.quantity if match.symbol is not None else ZERO
    ctx.emit(event)


def _add_fee_to_last_layer(ctx: ReplayContext, row: ReplayRow, fee: Decimal) -> bool:
    layers = ctx.result.fifo.get(row.key, [])
    if not layers:
        return False
    last = layers[-1]
    last["unit_cost"] = (last["qty"] * last["unit_cost"] + fee) / last["qty"] if last["qty"] > 0 else ZERO
    ctx.emit(
        ReplayEvent(
            kind="CONVERSION_IN_FEE",
            tx=row.tx,
            tx_dt=row.executed_at,
            symbol=row.symbol,
            quantity=row.quantity,
            fee=fee,
        )
    )
    return True


def apply_conversion_in(ctx: ReplayContext, row: ReplayRow) -> None:
    """Quantité et coût viennent de la sortie associée : seuls les frais restent à appliquer."""
    fee = Decimal(str(row.tx.fee or 0))
    if fee <= 0:
        return
    if ctx.config.fee_handling is FeeHandling.TX_CURRENCY:
        _add_fee_to_last_layer(ctx, row, fee * fx_rate(row.tx))
        return
    fee_currency = (row.tx.fee_currency or row.tx.currency or "EUR").upper()
    if fee_currency != ctx.portfolio_currency or not _add_fee_to_last_layer(ctx, row, fee):
        ctx.result.pending_fee_conversions.append((row.key, fee, fee_currency))
