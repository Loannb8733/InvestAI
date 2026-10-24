from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple

from app.domains.portfolio.classification import is_cash_like
from app.domains.portfolio.models import Asset


class Holdings(NamedTuple):
    assets: dict[str, Asset]
    quantities: dict[str, Decimal]
    cash_like: dict[str, Decimal]


def group_holdings(assets: Sequence[Asset]) -> Holdings:
    """Regroupe les lignes par symbole en sommant les quantités en Decimal ; les liquidités sont mises à part."""
    asset_map: dict[str, Asset] = {}
    qty_map: dict[str, Decimal] = {}
    cash_like_qty: dict[str, Decimal] = {}
    for a in assets:
        sym = a.symbol
        qty = Decimal(str(a.quantity))
        if is_cash_like(sym):
            cash_like_qty[sym] = cash_like_qty.get(sym, Decimal("0")) + qty
            continue
        if sym not in asset_map:
            asset_map[sym] = a
            qty_map[sym] = qty
        else:
            qty_map[sym] += qty
    return Holdings(asset_map, qty_map, cash_like_qty)
