"""Couches FIFO : chaque couche porte une quantité et son coût unitaire, la plus ancienne en tête."""

from datetime import datetime
from decimal import Decimal
from typing import TypedDict

ZERO = Decimal("0")


class Layer(TypedDict):
    """Une acquisition encore détenue, coûts exprimés dans la devise du portefeuille."""

    qty: Decimal
    unit_cost: Decimal
    unit_cost_base: Decimal
    currency: str
    fx_rate: Decimal
    is_paid: bool
    acquired_at: datetime | None


FifoKey = tuple[str, str]


def total_quantity(layers: list[Layer]) -> Decimal:
    """Quantité totale portée par des couches."""
    return sum((layer["qty"] for layer in layers), ZERO)


def consume_layers(layers: list[Layer], quantity: Decimal) -> tuple[Decimal, datetime | None]:
    """Retire `quantity` depuis la tête ; rend le coût retiré et la date de la plus ancienne couche touchée."""
    remaining = quantity
    cost = ZERO
    oldest: datetime | None = None
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


def extract_layers(layers: list[Layer], quantity: Decimal) -> list[Layer]:
    """Retire `quantity` depuis la tête et rend les couches extraites, coûts et dates conservés."""
    remaining = quantity
    extracted: list[Layer] = []
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
            remaining = ZERO
    return extracted
