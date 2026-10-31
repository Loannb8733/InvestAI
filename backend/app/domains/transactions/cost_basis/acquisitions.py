"""Étapes du rejeu hors conversions : achats, ventes, récompenses, transferts, dividendes."""

from decimal import Decimal

from app.domains.transactions.cost_basis.config import (
    FeeHandling,
    ReplayEvent,
    RewardBasis,
    UnmatchedTransferInPolicy,
)
from app.domains.transactions.cost_basis.context import (
    ONE,
    ReplayContext,
    ReplayRow,
    aware,
    fx_rate,
    transaction_currency,
)
from app.domains.transactions.cost_basis.layers import (
    ZERO,
    FifoKey,
    Layer,
    consume_layers,
    extract_layers,
    total_quantity,
)

TRANSIT_PREFIX = "__transit__"


def _buy_cost(ctx: ReplayContext, row: ReplayRow, base_cost: Decimal, fee: Decimal, rate: Decimal) -> Decimal:
    if fee <= 0:
        return base_cost
    if ctx.config.fee_handling is FeeHandling.TX_CURRENCY:
        return base_cost + fee * rate
    fee_currency = (row.tx.fee_currency or row.tx.currency or "EUR").upper()
    if fee_currency == ctx.portfolio_currency:
        return base_cost + fee
    ctx.result.pending_fee_conversions.append((row.key, fee, fee_currency))
    return base_cost


def apply_buy(ctx: ReplayContext, row: ReplayRow) -> None:
    """Crée une couche au coût de l'achat, frais compris quand ils sont dans la devise du portefeuille."""
    rate = fx_rate(row.tx)
    unit_cost_base = Decimal(str(row.tx.price or 0))
    fee = Decimal(str(row.tx.fee or 0))
    total_cost = _buy_cost(ctx, row, row.quantity * unit_cost_base * rate, fee, rate)
    ctx.add_layer(
        row.key,
        Layer(
            qty=row.quantity,
            unit_cost=total_cost / row.quantity if row.quantity > 0 else ZERO,
            unit_cost_base=unit_cost_base,
            currency=transaction_currency(row.tx),
            fx_rate=rate,
            is_paid=True,
            acquired_at=row.executed_at,
        ),
    )
    ctx.emit(
        ReplayEvent(
            kind="BUY",
            tx=row.tx,
            tx_dt=row.executed_at,
            symbol=row.symbol,
            quantity=row.quantity,
            price=unit_cost_base * rate,
            fee=fee * rate if ctx.config.fee_handling is FeeHandling.TX_CURRENCY else fee,
            total_cost=total_cost,
        )
    )


def apply_sell(ctx: ReplayContext, row: ReplayRow) -> None:
    """Consomme les couches les plus anciennes et émet la cession."""
    pool = ctx.result.fifo.get(row.key, [])
    pool_quantity = total_quantity(pool)
    if row.quantity > pool_quantity:
        ctx.warn(
            "Oversell: SELL qty=%s > pool=%s for %s@%s (tx_id=%s)",
            row.quantity,
            pool_quantity,
            row.symbol,
            row.exchange,
            row.tx.id,
        )
    cost_removed, oldest = consume_layers(pool, row.quantity)
    rate = fx_rate(row.tx)
    ctx.emit(
        ReplayEvent(
            kind="SELL",
            tx=row.tx,
            tx_dt=row.executed_at,
            symbol=row.symbol,
            quantity=row.quantity,
            price=Decimal(str(row.tx.price or 0)) * rate,
            fee=Decimal(str(row.tx.fee or 0)) * rate,
            cost_removed=cost_removed,
            oldest_acquired_at=aware(oldest),
        )
    )


def apply_reward(ctx: ReplayContext, row: ReplayRow) -> None:
    """Crée une couche au cours de réception, ou à coût nul selon le réglage."""
    rate = fx_rate(row.tx)
    price = Decimal(str(row.tx.price or 0)) if ctx.config.reward_basis is RewardBasis.MARKET_PRICE else ZERO
    ctx.add_layer(
        row.key,
        Layer(
            qty=row.quantity,
            unit_cost=price * rate,
            unit_cost_base=price,
            currency=transaction_currency(row.tx),
            fx_rate=rate,
            is_paid=price > ZERO,
            acquired_at=row.executed_at,
        ),
    )


def apply_transfer_out(ctx: ReplayContext, row: ReplayRow) -> None:
    """Déplace les couches les plus anciennes vers un lot en transit, repris par le transfert entrant."""
    fifo = ctx.result.fifo
    fifo[(row.symbol, f"{TRANSIT_PREFIX}{row.tx.id}")] = extract_layers(fifo.get(row.key, []), row.quantity)
    ctx.emit(
        ReplayEvent(kind="TRANSFER_OUT", tx=row.tx, tx_dt=row.executed_at, symbol=row.symbol, quantity=row.quantity)
    )


def _closest_transit(ctx: ReplayContext, row: ReplayRow) -> FifoKey | None:
    best: FifoKey | None = None
    best_gap: Decimal | None = None
    for key, layers in ctx.result.fifo.items():
        if key[0] == row.symbol and key[1].startswith(TRANSIT_PREFIX):
            gap = abs(total_quantity(layers) - row.quantity)
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best = key
    return best


def _recovered_layer(ctx: ReplayContext, row: ReplayRow) -> Layer:
    price = Decimal(str(row.tx.price or 0))
    if price > ZERO:
        rate = fx_rate(row.tx)
        unit_cost, unit_base, known = price * rate, price, True
    else:
        rate = ONE
        proxy = ctx.aid_to_avg_price.get(str(row.tx.asset_id), ZERO)
        if proxy <= ZERO:
            proxy = ctx.sym_avg_price.get(row.symbol, ZERO)
        unit_cost, unit_base, known = proxy, proxy, proxy > ZERO
    if not known:
        ctx.warn(
            "Unmatched TRANSFER_IN with no recoverable cost basis: tx_id=%s %s@%s qty=%s — using zero cost",
            row.tx.id,
            row.symbol,
            row.exchange,
            row.quantity,
        )
    return Layer(
        qty=row.quantity,
        unit_cost=unit_cost,
        unit_cost_base=unit_base,
        currency=transaction_currency(row.tx),
        fx_rate=rate,
        is_paid=known,
        acquired_at=row.executed_at,
    )


def _zero_cost_layer(row: ReplayRow) -> Layer:
    return Layer(
        qty=row.quantity,
        unit_cost=ZERO,
        unit_cost_base=ZERO,
        currency=transaction_currency(row.tx),
        fx_rate=ONE,
        is_paid=False,
        acquired_at=row.executed_at,
    )


def apply_transfer_in(ctx: ReplayContext, row: ReplayRow) -> None:
    """Reprend le lot en transit le plus proche, ou applique la politique des arrivées sans sortie."""
    fifo = ctx.result.fifo
    transit = _closest_transit(ctx, row)
    matched = transit is not None and bool(fifo[transit])
    if transit is not None and matched:
        layers = fifo.pop(transit)
        if ctx.config.trim_transfer_network_fee and total_quantity(layers) > row.quantity:
            layers = extract_layers(layers, row.quantity)
        fifo.setdefault(row.key, []).extend(layers)
    elif ctx.config.unmatched_transfer_in is UnmatchedTransferInPolicy.RECOVER:
        ctx.add_layer(row.key, _recovered_layer(ctx, row))
    else:
        ctx.add_layer(row.key, _zero_cost_layer(row))
    ctx.emit(
        ReplayEvent(
            kind="TRANSFER_IN",
            tx=row.tx,
            tx_dt=row.executed_at,
            symbol=row.symbol,
            quantity=row.quantity,
            matched=matched,
        )
    )


def apply_dividend(ctx: ReplayContext, row: ReplayRow) -> None:
    """Revenu en numéraire : aucune nouvelle couche, montant converti au taux saisi ou reporté."""
    amount = row.quantity * Decimal(str(row.tx.price or 0))
    if amount <= 0:
        return
    currency = transaction_currency(row.tx)
    if currency != ctx.portfolio_currency:
        if not row.tx.conversion_rate:
            ctx.result.pending_fee_conversions.append((f"__div__{row.symbol}", amount, currency))
            return
        amount *= Decimal(str(row.tx.conversion_rate))
    if amount > 0:
        income = ctx.result.dividend_income
        income[row.key] = income.get(row.key, ZERO) + amount
