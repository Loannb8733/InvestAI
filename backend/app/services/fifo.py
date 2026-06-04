"""Shared FIFO cost-basis primitives (single source of truth).

``metrics_service`` (displayed P&L / cost basis) and ``report_service`` (tax
2086 + sell-order estimates) both consume FIFO layers. The consume math used
to be duplicated as nested closures in each service, which risked the two
diverging — i.e. the displayed gain disagreeing with the tax-form gain.
These pure functions are the one implementation both call.

A "layer" is a dict ``{"qty": Decimal, "unit_cost": Decimal, "acquired_at": ...}``.
All functions mutate the passed ``layers`` list in place (front layers are
decremented / popped) and tolerate underflow (they stop when layers run out).
"""

from decimal import Decimal
from typing import Optional, Tuple

_ZERO = Decimal("0")


def consume_fifo(layers: list, qty: Decimal) -> Decimal:
    """Remove ``qty`` from the front of ``layers``; return total cost removed."""
    remaining = qty
    cost = _ZERO
    while remaining > 0 and layers:
        layer = layers[0]
        take = layer["qty"] if layer["qty"] <= remaining else remaining
        cost += take * layer["unit_cost"]
        remaining -= take
        if take >= layer["qty"]:
            layers.pop(0)
        else:
            layer["qty"] -= take
    return cost


def consume_fifo_with_dates(layers: list, qty: Decimal) -> Tuple[Decimal, Optional[object]]:
    """Like :func:`consume_fifo` but also return the oldest consumed acquired_at.

    The oldest layer's ``acquired_at`` drives the holding-period calc (tax M1).
    """
    remaining = qty
    cost = _ZERO
    oldest: Optional[object] = None
    while remaining > 0 and layers:
        layer = layers[0]
        if oldest is None:
            oldest = layer.get("acquired_at")
        take = layer["qty"] if layer["qty"] <= remaining else remaining
        cost += take * layer["unit_cost"]
        remaining -= take
        if take >= layer["qty"]:
            layers.pop(0)
        else:
            layer["qty"] -= take
    return cost, oldest


def extract_fifo_layers(layers: list, qty: Decimal) -> list:
    """Remove ``qty`` from ``layers``, returning the extracted layer copies.

    Used for transfers/conversions where the original unit costs (and any
    acquired_at) must be carried over to the destination's layers.
    """
    remaining = qty
    extracted: list = []
    while remaining > 0 and layers:
        layer = layers[0]
        if layer["qty"] <= remaining:
            extracted.append(layer.copy())
            remaining -= layer["qty"]
            layers.pop(0)
        else:
            partial = layer.copy()
            partial["qty"] = remaining
            extracted.append(partial)
            layer["qty"] -= remaining
            remaining = _ZERO
    return extracted
