"""Performance par plateforme des rapports."""

from collections.abc import Iterable, Mapping
from typing import Any, Protocol


class PlatformPosition(Protocol):
    """Ce que la synthèse lit d'une ligne du rapport."""

    exchange: str | None
    current_value: float
    total_invested: float
    total_fees: float


def _row(exchange: str) -> dict[str, Any]:
    return {"exchange": exchange, "total_value": 0.0, "total_invested": 0.0, "total_fees": 0.0, "count": 0}


def platform_analysis(
    positions: Iterable[PlatformPosition], sales: Mapping[str, Mapping[str, float]]
) -> list[dict[str, Any]]:
    """Gain latent et réalisé de chaque plateforme ; le rendement se rapporte à tout le coût qui y est passé."""
    rows: dict[str, dict[str, Any]] = {}
    for position in positions:
        row = rows.setdefault(position.exchange or "Autre", _row(position.exchange or "Autre"))
        row["total_value"] += position.current_value
        row["total_invested"] += position.total_invested
        row["total_fees"] += position.total_fees
        row["count"] += 1
    for exchange in sales:
        rows.setdefault(exchange, _row(exchange))
    for exchange, row in rows.items():
        sold = sales.get(exchange, {})
        row["net_pnl"] = row["total_value"] - row["total_invested"] + sold.get("realized", 0.0)
        cost = row["total_invested"] + sold.get("cost_sold", 0.0)
        row["roi_percent"] = row["net_pnl"] / cost * 100 if cost > 0 else 0
    return sorted(rows.values(), key=lambda row: row["total_value"], reverse=True)
