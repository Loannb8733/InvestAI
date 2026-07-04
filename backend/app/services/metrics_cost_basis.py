"""Cost-basis math extracted from metrics_service.

- ``_conversion_dest_unit_cost`` / ``_ci_price_in_portfolio_ccy``: per-unit cost
  helpers for crypto conversions (the fifo_replay engine keeps its own copies of
  the same tiny formulas; these remain the metrics-side originals the unit tests
  pin).
- ``compute_cump_pru``: the weighted-average (CUMP/PRU) cost basis — the
  alternative to the FIFO layer walk, computed straight from the transaction log.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


def _conversion_dest_unit_cost(
    cost_removed: Decimal,
    matched_qty: Decimal,
    recorded_price: Decimal,
) -> Decimal:
    """Cost basis per unit for a conversion destination.

    A crypto-to-crypto conversion is a disposal of the source plus a re-acquisition
    of the destination: the destination's cost basis is its market value on the
    conversion day, i.e. the **recorded CONVERSION_IN price**. We use that whenever
    it is known.

    The legacy model instead *carried* the source's consumed cost
    (``cost_removed / matched_qty``). A mis-matched or chained conversion can pair a
    large source cost with a tiny destination qty, concentrating cost into
    impossible per-unit values (observed up to ~500k EUR/BTC in prod) that overstate
    the cost basis and compound across conversion chains. We keep the carry only as
    a fallback for the rare case where the destination price was not recorded.
    """
    _Z = Decimal("0")
    if matched_qty <= _Z:
        return _Z
    if recorded_price > _Z:
        return recorded_price
    return cost_removed / matched_qty


def _ci_price_in_portfolio_ccy(price, conversion_rate) -> Decimal:
    """Recorded CONVERSION_IN price expressed in the portfolio currency.

    ``price`` is stored in the leg's own trade currency (e.g. a USD-quoted swap);
    ``conversion_rate`` is portfolio units per 1 unit of that currency (``None``
    means the price is already in the portfolio currency). Every other leg applies
    this same rate, so the conversion destination's cost basis must too — otherwise
    a USD-quoted CONVERSION_IN is carried as if it were EUR.
    """
    p = Decimal(str(price or 0))
    fx = Decimal(str(conversion_rate)) if conversion_rate else Decimal("1")
    return p * fx


def compute_cump_pru(
    all_txs: list,
    aid_to_symbol: Dict[str, str],
    aid_to_exchange: Dict[str, str],
) -> Dict[Tuple[str, str], Decimal]:
    """Compute CUMP (Weighted Average Cost) PRU per (symbol, exchange).

    Rules:
    1. PRU = (Σ buy_amount + fees) / Σ buy_qty  — fee-inclusive weighted average
    2. Sells reduce qty but never change PRU
    3. Position reset: when qty falls to 0, the next buy starts a fresh average
    """
    from app.models.transaction import TransactionType as TxType

    _ZERO = Decimal("0")
    state: Dict[Tuple[str, str], Dict] = {}

    for tx in all_txs:
        aid = str(tx.asset_id)
        sym = aid_to_symbol.get(aid, "")
        if not sym:
            continue
        exch = aid_to_exchange.get(aid, "")
        fkey = (sym, exch)

        if fkey not in state:
            state[fkey] = {
                "cost": _ZERO,
                "buy_qty": _ZERO,
                "current_qty": _ZERO,
                "pru": _ZERO,
                "needs_reset": False,
            }

        s = state[fkey]
        qty = Decimal(str(tx.quantity or 0))
        # Cost basis is tracked in the PORTFOLIO currency. The trade price/fee are
        # in ``tx.currency``, so convert them via the FX rate captured at execution
        # (``conversion_rate`` = portfolio units per 1 unit of tx currency; defaults
        # to 1 for same-currency trades). Without this, a USD/USDT-pair buy stored
        # the raw USD price as the PRU — ~8-9% above the EUR cost basis the FIFO
        # engine reports (which already applies this same rate), leaving the
        # displayed PRU inconsistent with the gain/loss. (FIN-01 parity.)
        fx = Decimal(str(tx.conversion_rate)) if getattr(tx, "conversion_rate", None) else Decimal("1")
        price = Decimal(str(tx.price or 0)) * fx
        fee = Decimal(str(tx.fee or 0)) * fx
        ttype = tx.transaction_type

        if ttype == TxType.BUY:
            if s["needs_reset"]:
                s["cost"] = _ZERO
                s["buy_qty"] = _ZERO
                s["needs_reset"] = False
            invested = qty * price + fee
            s["cost"] += invested
            s["buy_qty"] += qty
            s["current_qty"] += qty
            if s["buy_qty"] > _ZERO:
                s["pru"] = s["cost"] / s["buy_qty"]

        elif ttype == TxType.SELL:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)
            if s["current_qty"] <= _ZERO:
                s["current_qty"] = _ZERO
                s["needs_reset"] = True

        elif ttype == TxType.TRANSFER_IN:
            if price > _ZERO:
                s["cost"] += qty * price + fee
                s["buy_qty"] += qty
            elif s["pru"] > _ZERO:
                # F-06: a zero-price transfer-in of an already-held coin is an
                # internal wallet move; it inherits the running average cost so the
                # PRU stays stable instead of being diluted toward zero. (Unifies
                # behaviour with the FIFO engine's unmatched-transfer handling.)
                s["cost"] += qty * s["pru"]
                s["buy_qty"] += qty
            if s["buy_qty"] > _ZERO:
                s["pru"] = s["cost"] / s["buy_qty"]
            s["current_qty"] += qty

        elif ttype == TxType.TRANSFER_OUT:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)

        elif ttype in (TxType.STAKING_REWARD, TxType.AIRDROP):
            s["current_qty"] += qty

        elif ttype == TxType.CONVERSION_IN:
            if price > _ZERO:
                s["cost"] += qty * price
                s["buy_qty"] += qty
                if s["buy_qty"] > _ZERO:
                    s["pru"] = s["cost"] / s["buy_qty"]
            s["current_qty"] += qty

        elif ttype == TxType.CONVERSION_OUT:
            s["current_qty"] = max(_ZERO, s["current_qty"] - qty)

    return {fkey: s["pru"] for fkey, s in state.items() if s["pru"] > _ZERO and not s["needs_reset"]}
