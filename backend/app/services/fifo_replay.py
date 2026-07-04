"""Unified FIFO cost-basis replay engine.

Single chronological replay loop shared by the three former copies:

- ``metrics_service.get_portfolio_metrics`` (displayed P&L / cost basis),
- ``report_service.compute_tax_2086`` (French tax form 2086),
- ``report_service._estimate_rebalancing_tax`` (sell-order tax estimates).

The two original implementations had drifted apart. Every *legitimate*
difference (tax rules genuinely differ from display P&L) is an explicit
``ReplayConfig`` knob with the rationale documented on the knob; everything
else is one shared code path. Layer dicts carry the union of both callers'
fields, so an extra field costs nothing and never switches behaviour.

The engine does layer bookkeeping only. It never queries the DB (callers
pre-fetch and pre-scope transactions — one portfolio & all asset types for
metrics, all portfolios & crypto-only for tax) and it never computes gains:
disposal-like transactions emit :class:`ReplayEvent` records through
``on_event`` so each caller applies its own gain formula (per-layer P&L for
display, the art. 150 VH bis global formula for the 2086).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from app.models.transaction import TransactionType as TxType
from app.services.asset_classification import STABLECOIN_PEGS, is_stablecoin
from app.services.fifo import consume_fifo_with_dates, extract_fifo_layers

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

FifoKey = Tuple[str, str]  # (symbol, exchange)


# ---------------------------------------------------------------------------
# Config knobs — one per legitimate (or frozen-for-migration) divergence
# ---------------------------------------------------------------------------


class RewardBasis(str, Enum):
    """Cost basis for AIRDROP / STAKING_REWARD layers.

    MARKET_PRICE: recorded market price at receipt (display P&L — rewards are
    income at market value the day received). ZERO: zero-cost layer (2086 —
    no *prix d'acquisition à titre onéreux*, the conservative tax reading).
    """

    MARKET_PRICE = "market_price"
    ZERO = "zero"


class ConversionDestBasis(str, Enum):
    """Cost basis of the destination layer of a matched crypto conversion.

    RECORDED_PRICE: the recorded CONVERSION_IN market price (display — the FIN
    fix that stops mis-matched chains concentrating cost into runaway per-unit
    values, observed up to ~500k EUR/BTC). CARRY_COST: carry the consumed
    source cost (2086 — crypto-to-crypto is in *sursis d'imposition*, the
    basis must carry).
    """

    RECORDED_PRICE = "recorded_price"
    CARRY_COST = "carry_cost"


class UnmatchedTransferInPolicy(str, Enum):
    """Basis for a TRANSFER_IN with no matching transit layers.

    RECOVER: F-06 chain — row price, then the asset's stored avg_buy_price,
    then the symbol-wide average, then zero (display: zero basis would book
    the whole position as pure gain). ZERO: zero-cost layer (2086 — unproven
    basis is zero, the conservative i.e. more-tax reading).
    """

    RECOVER = "recover"
    ZERO = "zero"


class UnmatchedConversionOutPolicy(str, Enum):
    """What happens to source layers when a CONVERSION_OUT has no match.

    PRESERVE: keep the source layers untouched (display). CONSUME: consume the
    layers and emit a disposal event anyway — this reproduces the historical
    tax behaviour and exists only to freeze it during migration; the target
    is PRESERVE everywhere.
    """

    PRESERVE = "preserve"
    CONSUME = "consume"


class FeeHandling(str, Enum):
    """How BUY / CONVERSION_IN fees enter the cost basis.

    FEE_CURRENCY_AWARE: honour ``fee_currency`` — portfolio-currency fees go
    straight into the basis, others are deferred to
    ``ReplayResult.pending_fee_conversions`` for post-replay forex (display).
    TX_CURRENCY: assume the fee is in the transaction currency and convert it
    with the trade's ``conversion_rate`` (2086 behaviour; ``fee_currency`` is
    ignored, and a CONVERSION_IN fee with no existing layer is dropped).
    """

    FEE_CURRENCY_AWARE = "fee_currency_aware"
    TX_CURRENCY = "tx_currency"


@dataclass(frozen=True)
class ReplayConfig:
    portfolio_currency: str = "EUR"
    reward_basis: RewardBasis = RewardBasis.MARKET_PRICE
    conversion_dest_basis: ConversionDestBasis = ConversionDestBasis.RECORDED_PRICE
    unmatched_transfer_in: UnmatchedTransferInPolicy = UnmatchedTransferInPolicy.RECOVER
    unmatched_conversion_out: UnmatchedConversionOutPolicy = UnmatchedConversionOutPolicy.PRESERVE
    fee_handling: FeeHandling = FeeHandling.FEE_CURRENCY_AWARE
    # Trim transit layers down to the received qty on TRANSFER_IN (the excess
    # is a network fee burned on-chain, discarded from basis). False keeps the
    # historical tax behaviour (phantom qty + overstated basis) frozen.
    trim_transfer_network_fee: bool = True
    # Seed a synthetic at-peg layer when a stablecoin with no tracked history
    # is converted (e.g. USDC acquired off-platform then swapped into PAXG).
    seed_stablecoin_layers: bool = False
    # Use external_id ("convert_sell_<refid>" / "convert_buy_<refid>") as a
    # conversion-match fallback for rows synced before the notes-format fix.
    conversion_external_id_fallback: bool = True
    # Skip transactions with no executed_at (2086 behaviour); the display
    # replay keeps them, sorted to the epoch.
    skip_null_executed_at: bool = False


# ---------------------------------------------------------------------------
# Events & result
# ---------------------------------------------------------------------------


@dataclass
class ReplayEvent:
    """Emitted synchronously, in processing order, for ledger-relevant txs.

    ``kind`` is one of "BUY", "SELL", "CONVERSION_OUT", "CONVERSION_IN_FEE".
    Prices/fees/costs are in the portfolio currency. For conversions,
    ``matched``/``dest_symbol``/``dest_qty``/``dest_cost`` describe the
    destination layer the engine created (dest_cost is the cost that
    re-entered the book — the tax ledger adds it back).
    """

    kind: str
    tx: object
    tx_dt: Optional[datetime]
    symbol: str
    quantity: Decimal
    price: Decimal = _ZERO
    fee: Decimal = _ZERO
    total_cost: Decimal = _ZERO  # BUY: qty*price(+fee) entering the book
    cost_removed: Decimal = _ZERO  # SELL / CONVERSION_OUT
    oldest_acquired_at: Optional[datetime] = None
    matched: bool = False
    dest_symbol: Optional[str] = None
    dest_qty: Decimal = _ZERO
    dest_cost: Decimal = _ZERO


@dataclass
class ReplayResult:
    fifo: Dict[FifoKey, list] = field(default_factory=dict)
    orphan_transit: Dict[FifoKey, list] = field(default_factory=dict)
    events: List[ReplayEvent] = field(default_factory=list)
    # (key-or-"__div__SYM", amount, currency) — resolved post-replay by the
    # metrics caller with live forex rates (exact historical format).
    pending_fee_conversions: List[tuple] = field(default_factory=list)
    dividend_income: Dict[FifoKey, Decimal] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sort_transactions(txs: list) -> list:
    """THE canonical replay ordering.

    ``(executed_at ?? epoch, TRANSFER_OUT first, str(id))`` — TRANSFER_OUT must
    run before a same-timestamp TRANSFER_IN so the transit layers exist when
    the TRANSFER_IN looks for them, and ``str(id)`` makes equal-timestamp
    ordering deterministic across runs (bare SQL ``ORDER BY executed_at``
    is not).
    """

    def _key(tx):
        dt = tx.executed_at or _EPOCH
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt, 0 if tx.transaction_type == TxType.TRANSFER_OUT else 1, str(tx.id))

    return sorted(txs, key=_key)


def conversion_dest_unit_cost(cost_removed: Decimal, matched_qty: Decimal, recorded_price: Decimal) -> Decimal:
    """RECORDED_PRICE policy: destination basis = recorded market price, with
    the carried source cost kept only as a fallback when no price was recorded
    (see ConversionDestBasis docstring for the runaway-basis rationale)."""
    if matched_qty <= _ZERO:
        return _ZERO
    if recorded_price > _ZERO:
        return recorded_price
    return cost_removed / matched_qty


def _fx(tx) -> Decimal:
    return Decimal(str(tx.conversion_rate)) if tx.conversion_rate else _ONE


def _ci_price_in_portfolio_ccy(price, conversion_rate) -> Decimal:
    p = Decimal(str(price or 0))
    fx = Decimal(str(conversion_rate)) if conversion_rate else _ONE
    return p * fx


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def replay(
    txs: list,
    aid_to_symbol: Dict[str, str],
    config: ReplayConfig,
    *,
    aid_to_avg_price: Optional[Dict[str, Decimal]] = None,
    sym_avg_price: Optional[Dict[str, Decimal]] = None,
    usd_to_portfolio: Optional[Decimal] = None,
    on_event: Optional[Callable[[ReplayEvent], None]] = None,
) -> ReplayResult:
    """Run the chronological FIFO replay over pre-fetched, pre-sorted ``txs``.

    ``txs`` is processed in the given order — callers decide the ordering
    (use :func:`sort_transactions` for the canonical deterministic one).
    Transactions whose ``asset_id`` is not in ``aid_to_symbol`` are skipped:
    the mapping defines the replay scope.
    """
    aid_to_avg_price = aid_to_avg_price or {}
    sym_avg_price = sym_avg_price or {}
    result = ReplayResult()
    fifo: Dict[FifoKey, list] = result.fifo
    portfolio_ccy = config.portfolio_currency.upper()

    def _emit(event: ReplayEvent) -> None:
        result.events.append(event)
        if on_event is not None:
            on_event(event)

    def _warn(msg: str, *args) -> None:
        logger.warning(msg, *args)
        result.warnings.append(msg % args if args else msg)

    conv_ins = [tx for tx in txs if tx.transaction_type == TxType.CONVERSION_IN]

    def _match_conversion_in(co_tx, src_sym: str) -> Tuple[Optional[str], Optional[str], Decimal, Decimal]:
        """Find the matching CONVERSION_IN for a CONVERSION_OUT.

        Returns (dest_symbol, dest_exchange, matched_qty, matched_price) where
        matched_price is the recorded destination price in portfolio currency.
        """
        notes = co_tx.notes or ""
        exch = co_tx.exchange or ""
        dest_sym: Optional[str] = None
        dest_exch: Optional[str] = None
        matched_qty = Decimal(str(co_tx.quantity))  # fallback
        matched_price = _ZERO

        if "crypto.com" in exch.lower():
            for ci in conv_ins:
                if (ci.notes or "") == notes and (ci.exchange or "") == exch:
                    dest_sym = aid_to_symbol.get(str(ci.asset_id), "")
                    dest_exch = (ci.exchange or "").strip()
                    matched_qty = Decimal(str(ci.quantity))
                    matched_price = _ci_price_in_portfolio_ccy(ci.price, getattr(ci, "conversion_rate", None))
                    break
            return dest_sym, dest_exch, matched_qty, matched_price

        # Kraken / generic: match trade_id suffix in notes
        m = re.search(r"trade_id:convert_sell_(\S+)", notes)
        if m:
            suffix = m.group(1)
            for ci in conv_ins:
                if f"convert_buy_{suffix}" in (ci.notes or ""):
                    candidate = aid_to_symbol.get(str(ci.asset_id), "")
                    # M3: destination must differ from source
                    if candidate and candidate != src_sym:
                        dest_sym = candidate
                        dest_exch = (ci.exchange or "").strip()
                        matched_qty = Decimal(str(ci.quantity))
                        matched_price = _ci_price_in_portfolio_ccy(ci.price, getattr(ci, "conversion_rate", None))
                    else:
                        _warn(
                            "Conversion match rejected: src=%s == dest=%s (suffix=%s, tx_id=%s)",
                            src_sym,
                            candidate,
                            suffix,
                            co_tx.id,
                        )
                    break

        if dest_sym is None and config.conversion_external_id_fallback:
            # Rows synced before the notes-format fix carry the refid only in
            # external_id ("convert_sell_<refid>" / "convert_buy_<refid>").
            ext_id = getattr(co_tx, "external_id", None) or ""
            if ext_id.startswith("convert_sell_"):
                suffix = ext_id[len("convert_sell_") :]
                for ci in conv_ins:
                    if (getattr(ci, "external_id", None) or "") == f"convert_buy_{suffix}":
                        candidate = aid_to_symbol.get(str(ci.asset_id), "")
                        if candidate and candidate != src_sym:
                            dest_sym = candidate
                            dest_exch = (ci.exchange or "").strip()
                            matched_qty = Decimal(str(ci.quantity))
                            matched_price = _ci_price_in_portfolio_ccy(ci.price, getattr(ci, "conversion_rate", None))
                        else:
                            _warn(
                                "Conversion match (ext_id fallback) rejected: src=%s == dest=%s (suffix=%s, tx_id=%s)",
                                src_sym,
                                candidate,
                                suffix,
                                co_tx.id,
                            )
                        break

        return dest_sym, dest_exch, matched_qty, matched_price

    # ---- Single-pass chronological processing ----
    for tx in txs:
        aid = str(tx.asset_id)
        if aid not in aid_to_symbol:
            continue  # out of the caller's replay scope
        if config.skip_null_executed_at and not tx.executed_at:
            continue

        sym = aid_to_symbol[aid]
        exch = (tx.exchange or "").strip()
        key: FifoKey = (sym, exch)
        qty = Decimal(str(tx.quantity))
        ttype = tx.transaction_type
        tx_dt = _aware(tx.executed_at)

        if ttype == TxType.BUY:
            # Cost basis is tracked in the PORTFOLIO currency: the trade price
            # is in the transaction currency, converted via the FX rate
            # captured at execution (conversion_rate = portfolio units per
            # 1 unit of tx currency; defaults to 1).
            tx_ccy = (tx.currency or "EUR").upper()
            tx_fx = _fx(tx)
            unit_cost_base = Decimal(str(tx.price or 0))
            total_cost = qty * unit_cost_base * tx_fx
            fee = Decimal(str(tx.fee or 0))
            if fee > 0:
                if config.fee_handling is FeeHandling.TX_CURRENCY:
                    total_cost += fee * tx_fx
                else:
                    fee_ccy = (tx.fee_currency or tx.currency or "EUR").upper()
                    if fee_ccy == portfolio_ccy:
                        total_cost += fee
                    else:
                        result.pending_fee_conversions.append((key, fee, fee_ccy))
            layer_unit = total_cost / qty if qty > 0 else _ZERO
            fifo.setdefault(key, []).append(
                {
                    "qty": qty,
                    "unit_cost": layer_unit,
                    "unit_cost_base": unit_cost_base,
                    "currency": tx_ccy,
                    "fx_rate": tx_fx,
                    "is_paid": True,
                    "acquired_at": tx_dt,
                }
            )
            _emit(
                ReplayEvent(
                    kind="BUY",
                    tx=tx,
                    tx_dt=tx_dt,
                    symbol=sym,
                    quantity=qty,
                    price=unit_cost_base * tx_fx,
                    fee=fee * tx_fx if config.fee_handling is FeeHandling.TX_CURRENCY else fee,
                    total_cost=total_cost,
                )
            )

        elif ttype == TxType.SELL:
            pool = fifo.get(key, [])
            pool_qty = sum(ly["qty"] for ly in pool)
            if qty > pool_qty:
                _warn("Oversell: SELL qty=%s > pool=%s for %s@%s (tx_id=%s)", qty, pool_qty, sym, exch, tx.id)
            cost_removed, oldest = consume_fifo_with_dates(pool, qty)
            tx_fx = _fx(tx)
            _emit(
                ReplayEvent(
                    kind="SELL",
                    tx=tx,
                    tx_dt=tx_dt,
                    symbol=sym,
                    quantity=qty,
                    price=Decimal(str(tx.price or 0)) * tx_fx,
                    fee=Decimal(str(tx.fee or 0)) * tx_fx,
                    cost_removed=cost_removed,
                    oldest_acquired_at=_aware(oldest),
                )
            )

        elif ttype in (TxType.AIRDROP, TxType.STAKING_REWARD):
            tx_ccy = (tx.currency or "EUR").upper()
            tx_fx = _fx(tx)
            if config.reward_basis is RewardBasis.MARKET_PRICE:
                reward_price = Decimal(str(tx.price or 0))
            else:
                reward_price = _ZERO
            fifo.setdefault(key, []).append(
                {
                    "qty": qty,
                    "unit_cost": reward_price * tx_fx,
                    "unit_cost_base": reward_price,
                    "currency": tx_ccy,
                    "fx_rate": tx_fx,
                    "is_paid": reward_price > _ZERO,
                    "acquired_at": tx_dt,
                }
            )

        elif ttype == TxType.TRANSFER_OUT:
            # Move the oldest layers into a transit pool — the matching
            # TRANSFER_IN picks them up (basis travels, no cost change).
            extracted = extract_fifo_layers(fifo.get(key, []), qty)
            fifo[(sym, f"__transit__{tx.id}")] = extracted
            _emit(ReplayEvent(kind="TRANSFER_OUT", tx=tx, tx_dt=tx_dt, symbol=sym, quantity=qty))

        elif ttype == TxType.TRANSFER_IN:
            # Best transit match: same symbol, closest total qty.
            matched_transit = None
            best_diff = None
            for tkey, tlayers in list(fifo.items()):
                if tkey[0] == sym and tkey[1].startswith("__transit__"):
                    diff = abs(sum(ly["qty"] for ly in tlayers) - qty)
                    if best_diff is None or diff < best_diff:
                        best_diff = diff
                        matched_transit = tkey
            if matched_transit and fifo[matched_transit]:
                transit_layers = fifo.pop(matched_transit)
                transit_qty = sum(ly["qty"] for ly in transit_layers)
                if config.trim_transfer_network_fee and transit_qty > qty:
                    # Network fee burned on-chain: keep only the received qty,
                    # discard the excess from the basis.
                    transit_layers = extract_fifo_layers(transit_layers, qty)
                fifo.setdefault(key, []).extend(transit_layers)
                _emit(ReplayEvent(kind="TRANSFER_IN", tx=tx, tx_dt=tx_dt, symbol=sym, quantity=qty, matched=True))
            else:
                if config.unmatched_transfer_in is UnmatchedTransferInPolicy.RECOVER:
                    # F-06 recovery chain: row price -> stored avg_buy_price ->
                    # symbol-wide average -> zero.
                    tx_ccy = (tx.currency or "EUR").upper()
                    tx_price = Decimal(str(tx.price or 0))
                    if tx_price > _ZERO:
                        tx_fx = _fx(tx)
                        unit_cost = tx_price * tx_fx
                        unit_base = tx_price
                        cost_known = True
                    else:
                        proxy = aid_to_avg_price.get(aid, _ZERO)
                        if proxy <= _ZERO:
                            proxy = sym_avg_price.get(sym, _ZERO)
                        tx_fx = _ONE
                        unit_cost = proxy
                        unit_base = proxy
                        cost_known = proxy > _ZERO
                    if not cost_known:
                        _warn(
                            "Unmatched TRANSFER_IN with no recoverable cost basis: "
                            "tx_id=%s %s@%s qty=%s — using zero cost",
                            tx.id,
                            sym,
                            exch,
                            qty,
                        )
                    fifo.setdefault(key, []).append(
                        {
                            "qty": qty,
                            "unit_cost": unit_cost,
                            "unit_cost_base": unit_base,
                            "currency": tx_ccy,
                            "fx_rate": tx_fx,
                            "is_paid": cost_known,
                            "acquired_at": tx_dt,
                        }
                    )
                else:  # ZERO (tax: unproven basis is zero — conservative)
                    fifo.setdefault(key, []).append(
                        {
                            "qty": qty,
                            "unit_cost": _ZERO,
                            "unit_cost_base": _ZERO,
                            "currency": (tx.currency or "EUR").upper(),
                            "fx_rate": _ONE,
                            "is_paid": False,
                            "acquired_at": tx_dt,
                        }
                    )
                _emit(ReplayEvent(kind="TRANSFER_IN", tx=tx, tx_dt=tx_dt, symbol=sym, quantity=qty, matched=False))

        elif ttype == TxType.CONVERSION_OUT:
            dest_sym, dest_exch, matched_ci_qty, matched_ci_price = _match_conversion_in(tx, sym)
            tx_ccy = (tx.currency or "EUR").upper()
            tx_fx = _fx(tx)
            price_pf = Decimal(str(tx.price or 0)) * tx_fx
            fee_pf = Decimal(str(tx.fee or 0)) * tx_fx

            if dest_sym is None and config.unmatched_conversion_out is UnmatchedConversionOutPolicy.PRESERVE:
                # Unmatched: qty leaves but the cost layers stay on the source
                # (destroying them here would silently erase basis).
                _warn(
                    "Unmatched CONVERSION_OUT: tx_id=%s src=%s qty=%s exchange=%s notes='%s' "
                    "— cost preserved on source",
                    tx.id,
                    sym,
                    qty,
                    exch,
                    tx.notes or "",
                )
                _emit(
                    ReplayEvent(
                        kind="CONVERSION_OUT",
                        tx=tx,
                        tx_dt=tx_dt,
                        symbol=sym,
                        quantity=qty,
                        price=price_pf,
                        fee=fee_pf,
                        matched=False,
                    )
                )
                continue

            pool = fifo.get(key, [])
            pool_qty = sum(ly["qty"] for ly in pool)

            if dest_sym is not None and pool_qty == _ZERO and config.seed_stablecoin_layers and is_stablecoin(sym):
                # Stablecoin with no tracked history: seed a synthetic at-peg
                # layer so basis propagates (e.g. USDC bought off-platform).
                if STABLECOIN_PEGS.get(sym) == "EUR":
                    per_unit = _ONE
                    layer_ccy = "EUR"
                    layer_fx = _ONE
                else:
                    per_unit = Decimal(str(usd_to_portfolio or 0)) or _ONE
                    layer_ccy = "USD"
                    layer_fx = per_unit
                fifo.setdefault(key, []).append(
                    {
                        "qty": qty,
                        "unit_cost": per_unit,
                        "unit_cost_base": _ONE,
                        "currency": layer_ccy,
                        "fx_rate": layer_fx,
                        "is_paid": True,
                        "acquired_at": tx_dt,
                    }
                )
                pool = fifo[key]
                pool_qty = qty
                logger.info(
                    "Seeded synthetic %s layer for stablecoin %s@%s qty=%s unit_cost=%s (tx_id=%s)",
                    layer_ccy,
                    sym,
                    exch,
                    qty,
                    per_unit,
                    tx.id,
                )
            elif dest_sym is not None and qty > pool_qty:
                _warn(
                    "Over-conversion: CONVERSION_OUT qty=%s > pool=%s for %s@%s (tx_id=%s)",
                    qty,
                    pool_qty,
                    sym,
                    exch,
                    tx.id,
                )

            cost_removed, oldest = consume_fifo_with_dates(pool, qty)

            dest_cost = _ZERO
            if dest_sym is not None and matched_ci_qty > 0:
                dest_key: FifoKey = (dest_sym, dest_exch or exch)
                if cost_removed > 0:
                    if config.conversion_dest_basis is ConversionDestBasis.RECORDED_PRICE:
                        dest_unit = conversion_dest_unit_cost(cost_removed, matched_ci_qty, matched_ci_price)
                    else:  # CARRY_COST
                        dest_unit = cost_removed / matched_ci_qty
                    fifo.setdefault(dest_key, []).append(
                        {
                            "qty": matched_ci_qty,
                            "unit_cost": dest_unit,
                            "unit_cost_base": dest_unit / tx_fx if tx_fx else dest_unit,
                            "currency": tx_ccy,
                            "fx_rate": tx_fx,
                            "is_paid": True,
                            "acquired_at": tx_dt,
                        }
                    )
                    dest_cost = cost_removed
                else:
                    # Zero-cost source (e.g. an airdrop converted onward)
                    fifo.setdefault(dest_key, []).append(
                        {
                            "qty": matched_ci_qty,
                            "unit_cost": _ZERO,
                            "unit_cost_base": _ZERO,
                            "currency": tx_ccy,
                            "fx_rate": tx_fx,
                            "is_paid": False,
                            "acquired_at": tx_dt,
                        }
                    )

            _emit(
                ReplayEvent(
                    kind="CONVERSION_OUT",
                    tx=tx,
                    tx_dt=tx_dt,
                    symbol=sym,
                    quantity=qty,
                    price=price_pf,
                    fee=fee_pf,
                    cost_removed=cost_removed,
                    oldest_acquired_at=_aware(oldest),
                    matched=dest_sym is not None,
                    dest_symbol=dest_sym,
                    dest_qty=matched_ci_qty if dest_sym is not None else _ZERO,
                    dest_cost=dest_cost,
                )
            )

        elif ttype == TxType.CONVERSION_IN:
            # Qty/cost already handled by the matching CONVERSION_OUT; only
            # the fee needs applying.
            fee = Decimal(str(tx.fee or 0))
            if fee <= 0:
                continue
            if config.fee_handling is FeeHandling.TX_CURRENCY:
                fee_pf = fee * _fx(tx)
                layers = fifo.get(key, [])
                if layers:
                    last = layers[-1]
                    old_total = last["qty"] * last["unit_cost"]
                    last["unit_cost"] = (old_total + fee_pf) / last["qty"] if last["qty"] > 0 else _ZERO
                    _emit(
                        ReplayEvent(kind="CONVERSION_IN_FEE", tx=tx, tx_dt=tx_dt, symbol=sym, quantity=qty, fee=fee_pf)
                    )
                # else: silently dropped (frozen historical tax behaviour)
            else:
                fee_ccy = (tx.fee_currency or tx.currency or "EUR").upper()
                if fee_ccy == portfolio_ccy:
                    layers = fifo.get(key, [])
                    if layers:
                        last = layers[-1]
                        old_total = last["qty"] * last["unit_cost"]
                        last["unit_cost"] = (old_total + fee) / last["qty"] if last["qty"] > 0 else _ZERO
                        _emit(
                            ReplayEvent(kind="CONVERSION_IN_FEE", tx=tx, tx_dt=tx_dt, symbol=sym, quantity=qty, fee=fee)
                        )
                    else:
                        # No layer yet — the CONVERSION_OUT creates it later;
                        # defer for post-replay application.
                        result.pending_fee_conversions.append((key, fee, fee_ccy))
                else:
                    result.pending_fee_conversions.append((key, fee, fee_ccy))

        elif ttype == TxType.DIVIDEND:
            # Cash income — no new shares; tracked for Total Return.
            div_amount = qty * Decimal(str(tx.price or 0))
            if div_amount > 0:
                tx_ccy = (tx.currency or "EUR").upper()
                if tx_ccy != portfolio_ccy and tx.conversion_rate:
                    div_amount *= Decimal(str(tx.conversion_rate))
                elif tx_ccy != portfolio_ccy:
                    # Resolved later with live forex rates (exact legacy format).
                    result.pending_fee_conversions.append((f"__div__{sym}", div_amount, tx_ccy))
                    div_amount = _ZERO
                if div_amount > 0:
                    result.dividend_income[key] = result.dividend_income.get(key, _ZERO) + div_amount

        # STAKING / UNSTAKING and any other types: no cost-basis impact.

    # Split orphan transit pools out of the final book (observability).
    for tkey in [k for k in fifo if k[1].startswith("__transit__")]:
        result.orphan_transit[tkey] = fifo.pop(tkey)

    return result
