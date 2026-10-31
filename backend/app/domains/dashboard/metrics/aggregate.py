"""Agrégat du tableau de bord : tous les portefeuilles d'un utilisateur, calcul sans accès à la base."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domains.portfolio.models import Portfolio
from app.domains.transactions.cost_basis.layers import ZERO

_TOP_COUNT = 5

EMPTY_DASHBOARD: dict[str, Any] = {
    "total_value": 0.0,
    "total_invested": 0.0,
    "net_capital": 0.0,
    "total_gain_loss": 0.0,
    "total_gain_loss_percent": 0.0,
    "net_gain_loss": 0.0,
    "net_gain_loss_percent": 0.0,
    "daily_change": 0.0,
    "daily_change_percent": 0.0,
    "portfolios_count": 0,
    "assets_count": 0,
    "allocation": [],
    "top_performers": [],
    "worst_performers": [],
}


def gain_figures(unrealized: Decimal, realized: Decimal, invested: Decimal, dividends: Decimal) -> dict[str, float]:
    """Gain total, frais déduits : latent (valeur moins coût restant) et réalisé (ventes moins coût sorti)."""
    gain = unrealized + realized
    return {
        "total_gain_loss": float(gain),
        "total_gain_loss_percent": float(gain / invested * 100) if invested > 0 else 0.0,
        "total_return": float(gain + dividends),
    }


HISTORY_UNAVAILABLE: dict[str, float] = {
    "total_invested_all_time": 0.0,
    "total_sold_fiat": 0.0,
    "realized_gains": 0.0,
    "total_fees": 0.0,
}


@dataclass
class DashboardTotals:
    """Cumul des métriques et historiques de chaque portefeuille."""

    value: Decimal = ZERO
    unrealized: Decimal = ZERO
    invested: Decimal = ZERO
    sold: Decimal = ZERO
    realized: Decimal = ZERO
    fees: Decimal = ZERO
    liquidity: Decimal = ZERO
    dividends: Decimal = ZERO
    forex_stale: bool = False
    unpriced: set[str] = field(default_factory=set)
    assets: list[dict[str, Any]] = field(default_factory=list)
    stablecoins: list[dict[str, Any]] = field(default_factory=list)

    def add(self, portfolio: Portfolio, metrics: dict[str, Any], history: dict[str, Any]) -> None:
        """Ajoute un portefeuille ; ses soldes en espèces comptent dans la liquidité."""
        self.value += Decimal(str(metrics["total_value"]))
        self.unrealized += Decimal(str(metrics["unrealized_gain"]))
        self.unpriced.update(metrics.get("unpriced_symbols", []))
        self.invested += Decimal(str(history["total_invested_all_time"]))
        self.sold += Decimal(str(history.get("total_sold_fiat", 0)))
        self.realized += Decimal(str(history.get("realized_gains", 0)))
        self.fees += Decimal(str(history.get("total_fees", 0)))
        self.liquidity += Decimal(str(metrics.get("available_liquidity", 0)))
        self.liquidity += sum((Decimal(str(amount)) for amount in (portfolio.cash_balances or {}).values()), ZERO)
        self.assets.extend(metrics["assets"])
        self.stablecoins.extend(metrics.get("stablecoins", []))
        self.dividends += Decimal(str(metrics.get("total_dividend_income", 0)))
        self.forex_stale = self.forex_stale or metrics.get("forex_stale", False)


def aggregate_by_symbol(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fusionne les positions d'un même symbole, toutes plateformes confondues."""
    aggregated: dict[str, dict[str, Any]] = {}
    for asset in assets:
        entry = aggregated.setdefault(
            asset["symbol"],
            {
                "symbol": asset["symbol"],
                "name": asset["name"],
                "asset_type": asset["asset_type"],
                "current_price": asset.get("current_price"),
                "total_invested": 0.0,
                "current_value": 0.0,
                "total_quantity": 0.0,
            },
        )
        entry["total_invested"] += asset["total_invested"]
        entry["current_value"] += asset["current_value"]
        entry["total_quantity"] += asset.get("quantity", 0)
    return aggregated


def symbols_by_type(aggregated: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Symboles regroupés par type d'actif."""
    grouped: dict[str, list[str]] = {}
    for entry in aggregated.values():
        grouped.setdefault(entry["asset_type"], []).append(entry["symbol"])
    return grouped


def apply_period_changes(aggregated: dict[str, dict[str, Any]], changes: dict[str, float]) -> None:
    """Variation de période de chaque symbole ; sans historique, gain rapporté au coût."""
    for entry in aggregated.values():
        symbol = entry["symbol"].upper()
        invested = entry["total_invested"]
        fallback = (entry["current_value"] - invested) / invested * 100 if invested > 0 else 0.0
        entry["period_change_percent"] = changes.get(symbol, fallback)


def _period_amount(entry: dict[str, Any]) -> float:
    percent = entry["period_change_percent"]
    if percent <= -100:
        return float(-entry["current_value"])
    return float(entry["current_value"] * percent / (100 + percent))


def _performer(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": entry["symbol"],
        "name": entry["name"],
        "asset_type": entry["asset_type"],
        "gain_loss_percent": round(entry["period_change_percent"], 2),
        "current_value": entry["current_value"],
    }


def _allocation(assets: list[dict[str, Any]], total_value: float) -> list[dict[str, Any]]:
    by_type: dict[str, float] = {}
    for asset in assets:
        by_type[asset["asset_type"]] = by_type.get(asset["asset_type"], 0.0) + asset["current_value"]
    allocation = [
        {"type": kind, "value": value, "percentage": value / total_value * 100 if total_value > 0 else 0}
        for kind, value in by_type.items()
    ]
    allocation.sort(key=lambda entry: entry["value"], reverse=True)
    return allocation


def project_aggregated_assets(aggregated: list[dict[str, Any]], total_value: float) -> list[dict[str, Any]]:
    """Répartition par symbole détenu, relue par le rebalancement, les alertes, le résumé Earn et les rapports."""
    return [
        {
            "symbol": entry["symbol"],
            "name": entry["name"],
            "asset_type": entry["asset_type"],
            "current_value": entry["current_value"],
            "current_price": entry.get("current_price"),
            "quantity": entry["total_quantity"],
            "total_invested": entry["total_invested"],
            "avg_buy_price": entry["total_invested"] / entry["total_quantity"] if entry["total_quantity"] > 0 else 0.0,
            "gain_loss_percent": round(entry.get("period_change_percent", 0), 2),
            "percentage": round(entry["current_value"] / total_value * 100 if total_value > 0 else 0, 2),
        }
        for entry in aggregated
        if entry["current_value"] > 0
    ]


def _pnl_breakdown(totals: DashboardTotals) -> dict[str, Any]:
    total = totals.unrealized + totals.realized
    return {
        "realized_pnl": float(totals.realized),
        "unrealized_pnl": float(totals.unrealized),
        "total_pnl": float(total),
        "total_fees": float(totals.fees),
        "net_pnl": float(total),
        "is_all_time": True,
    }


def _weighted_period_change(aggregated: list[dict[str, Any]], total_value: float) -> float:
    if total_value <= 0:
        return 0.0
    return sum(
        (entry.get("period_change_percent", 0) * (entry["current_value"] / total_value) for entry in aggregated), 0.0
    )


def build_dashboard_summary(
    portfolios_count: int,
    totals: DashboardTotals,
    aggregated: list[dict[str, Any]],
    period_changes: dict[str, float],
) -> dict[str, Any]:
    """Assemble les chiffres du tableau de bord ; meilleurs et moins bons sont classés en euros de la période."""
    total_value = float(totals.value)
    gain = gain_figures(totals.unrealized, totals.realized, totals.invested, totals.dividends)
    period_percent = _weighted_period_change(aggregated, total_value)
    gainers = sorted((e for e in aggregated if e["period_change_percent"] > 0), key=_period_amount, reverse=True)
    losers = sorted((e for e in aggregated if e["period_change_percent"] < 0), key=_period_amount)
    assets = totals.assets
    return {
        "total_value": total_value,
        "total_invested": float(totals.invested),
        "net_capital": float(totals.invested - totals.sold),
        "total_gain_loss": gain["total_gain_loss"],
        "total_gain_loss_percent": gain["total_gain_loss_percent"],
        "total_return": gain["total_return"],
        "net_gain_loss": gain["total_gain_loss"],
        "net_gain_loss_percent": gain["total_gain_loss_percent"],
        "daily_change": sum(a["current_value"] * a.get("change_percent_24h", 0) / 100 for a in assets),
        "daily_change_percent": (
            sum((a["current_value"] / total_value) * a.get("change_percent_24h", 0) for a in assets)
            if total_value > 0
            else 0.0
        ),
        "period_change": total_value * period_percent / 100 if period_percent else 0.0,
        "period_change_percent": period_percent,
        "portfolios_count": portfolios_count,
        "assets_count": len({a["symbol"] for a in assets}),
        "allocation": _allocation(assets, total_value),
        "top_performers": [_performer(entry) for entry in gainers[:_TOP_COUNT]],
        "worst_performers": [_performer(entry) for entry in losers[:_TOP_COUNT]],
        "available_liquidity": float(totals.liquidity),
        "assets": assets,
        "stablecoins": totals.stablecoins,
        "total_dividend_income": float(totals.dividends),
        "period_changes": period_changes,
        "aggregated_assets": project_aggregated_assets(aggregated, total_value),
        "pnl_data": _pnl_breakdown(totals),
        "forex_stale": totals.forex_stale,
        "unpriced_symbols": sorted(totals.unpriced),
    }
