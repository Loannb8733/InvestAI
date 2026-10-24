from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.reports.classes import CRYPTO_ASSET_CLASSES, CRYPTO_CLASS_LABELS
from app.domains.reports.tax import TAX_MODE
from app.domains.transactions.models import Transaction
from app.services import fifo_replay
from app.services.metrics_service import metrics_service

_ZERO = Decimal("0")
_DUST_VALUE = 0.10
_MIN_DRIFT_EUR = 1.0
_PFU_RATE = 0.30

FifoLayers = dict[tuple[str, str], list[Any]]


@dataclass
class RebalanceOrder:
    """Achat ou vente d'une classe crypto ; drift_pct = actuel - cible, estimated_tax = PFU 30 % (ventes seules)."""

    category: str
    action: str
    amount_eur: float
    current_pct: float
    target_pct: float
    drift_pct: float
    estimated_gain: float = 0.0
    estimated_tax: float = 0.0


@dataclass
class RebalancingReport:
    total_value: float
    categories: list[dict[str, Any]]
    orders: list[RebalanceOrder]
    total_sell_amount: float = 0.0
    total_buy_amount: float = 0.0
    total_estimated_gain: float = 0.0
    total_estimated_tax: float = 0.0
    hhi_before: float = 0.0
    hhi_after: float = 0.0


def _group_by_class(
    allocations: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
    class_totals: dict[str, float] = defaultdict(float)
    class_assets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in allocations:
        if a.get("asset_type") != "crypto":
            continue
        sym = a.get("symbol", "").upper()
        val = a.get("current_value", 0.0)
        if val < _DUST_VALUE:
            continue
        cls = CRYPTO_ASSET_CLASSES.get(sym, "Other")
        class_totals[cls] += val
        class_assets[cls].append({**a, "value": val})
    return class_totals, class_assets


def _categories(
    all_classes: set[str],
    class_totals: dict[str, float],
    crypto_total: float,
    target_allocations: dict[str, float],
) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for cls in sorted(all_classes):
        current_val = class_totals.get(cls, 0.0)
        current_pct = (current_val / crypto_total * 100) if crypto_total > 0 else 0.0
        target_pct = target_allocations.get(cls, 0.0) * 100
        categories.append(
            {
                "category": cls,
                "label": CRYPTO_CLASS_LABELS.get(cls, cls),
                "current_value": round(current_val, 2),
                "current_pct": round(current_pct, 2),
                "target_pct": round(target_pct, 2),
                "drift_pct": round(current_pct - target_pct, 2),
                "drift_eur": round(current_val - crypto_total * target_allocations.get(cls, 0.0), 2),
            }
        )
    return categories


def _orders(categories: list[dict[str, Any]]) -> list[RebalanceOrder]:
    orders: list[RebalanceOrder] = []
    for cat in categories:
        drift_eur = cat["drift_eur"]
        if abs(drift_eur) < _MIN_DRIFT_EUR:
            continue
        action = "sell" if drift_eur > 0 else "buy"
        orders.append(
            RebalanceOrder(
                category=cat["category"],
                action=action,
                amount_eur=round(abs(drift_eur), 2),
                current_pct=cat["current_pct"],
                target_pct=cat["target_pct"],
                drift_pct=cat["drift_pct"],
            )
        )
    return orders


def _build_report(
    total_value: float,
    categories: list[dict[str, Any]],
    orders: list[RebalanceOrder],
    hhi_before: float,
    hhi_after: float,
) -> RebalancingReport:
    total_sell = sum(o.amount_eur for o in orders if o.action == "sell")
    total_buy = sum(o.amount_eur for o in orders if o.action == "buy")
    total_gain = sum(o.estimated_gain for o in orders)
    total_tax = sum(o.estimated_tax for o in orders)
    return RebalancingReport(
        total_value=round(total_value, 2),
        categories=categories,
        orders=orders,
        total_sell_amount=round(total_sell, 2),
        total_buy_amount=round(total_buy, 2),
        total_estimated_gain=round(total_gain, 2),
        total_estimated_tax=round(total_tax, 2),
        hhi_before=round(hhi_before, 1),
        hhi_after=round(hhi_after, 1),
    )


def _stablecoin_allocations(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": s["symbol"],
            "asset_type": "crypto",
            "current_value": s["value"],
            "current_price": s["unit_price"],
            "quantity": s["quantity"],
        }
        for s in dashboard.get("stablecoins", [])
    ]


def _unit_price(asset_info: dict[str, Any]) -> Decimal:
    if asset_info.get("current_price"):
        return Decimal(str(asset_info["current_price"]))
    quantity = Decimal(str(asset_info.get("quantity") or 0))
    return Decimal(str(asset_info.get("value", 0))) / quantity if quantity > 0 else _ZERO


def _symbol_layers(fifo: FifoLayers, sym: str) -> list[Any]:
    sym_layers: list[Any] = []
    for fkey, layers in fifo.items():
        if fkey[0] == sym and not fkey[1].startswith("__transit__"):
            sym_layers.extend(layers)
    return sym_layers


def _walk_layers(layers: list[Any], qty_to_sell: Decimal, current_price: Decimal, estimated_gain: Decimal) -> Decimal:
    remaining = qty_to_sell
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer["qty"], remaining)
        gain = take * (current_price - layer["unit_cost"])
        estimated_gain += gain
        remaining -= take
    return estimated_gain


def _estimate_order_gain(order: RebalanceOrder, assets_in_class: list[dict[str, Any]], fifo: FifoLayers) -> Decimal:
    sell_remaining = Decimal(str(order.amount_eur))
    estimated_gain = _ZERO
    for asset_info in sorted(assets_in_class, key=lambda a: a.get("value", 0), reverse=True):
        if sell_remaining <= 0:
            break
        sym = asset_info.get("symbol", "").upper()
        current_price = _unit_price(asset_info)
        if current_price <= 0:
            continue
        sym_layers = _symbol_layers(fifo, sym)
        asset_value = Decimal(str(asset_info.get("value", 0)))
        sell_from_this = min(sell_remaining, asset_value)
        qty_to_sell = sell_from_this / current_price
        estimated_gain = _walk_layers(sym_layers, qty_to_sell, current_price, estimated_gain)
        sell_remaining -= sell_from_this
    return estimated_gain


class RebalancingMixin:
    async def get_rebalancing_report(
        self,
        db: AsyncSession,
        user_id: str,
        target_allocations: dict[str, float],
        currency: str = "EUR",
        estimate_tax: bool = True,
    ) -> RebalancingReport:
        """Ordres pour atteindre target_allocations (fractions par classe crypto, stablecoins détenus compris).

        Les actifs sous 0,10 € sont ignorés. L'impôt des ventes est estimé par FIFO (désactivable via
        estimate_tax) au cours courant, à défaut au prix unitaire valeur / quantité.
        """
        dashboard = await metrics_service.get_user_dashboard_metrics(
            db,
            user_id,
            currency=currency,
        )
        total_value = dashboard.get("total_value", 0.0)
        if total_value <= 0:
            return RebalancingReport(total_value=0, categories=[], orders=[])

        allocations = dashboard.get("aggregated_assets", []) + _stablecoin_allocations(dashboard)
        class_totals, class_assets = _group_by_class(allocations)
        crypto_total = sum(class_totals.values())
        if crypto_total <= 0:
            return RebalancingReport(total_value=total_value, categories=[], orders=[])

        all_classes = set(list(target_allocations.keys()) + list(class_totals.keys()))
        categories = _categories(all_classes, class_totals, crypto_total, target_allocations)
        orders = _orders(categories)

        if estimate_tax and any(o.action == "sell" for o in orders):
            await self._estimate_rebalancing_tax(db, user_id, orders, class_assets, currency)

        weights_before = [(v / crypto_total * 100) for v in class_totals.values()]
        hhi_before = sum(w**2 for w in weights_before)
        weights_after = [target_allocations.get(cls, 0.0) * 100 for cls in all_classes]
        hhi_after = sum(w**2 for w in weights_after)

        return _build_report(total_value, categories, orders, hhi_before, hhi_after)

    async def _estimate_rebalancing_tax(
        self,
        db: AsyncSession,
        user_id: str,
        orders: list[RebalanceOrder],
        class_assets: dict[str, list[dict[str, Any]]],
        currency: str,
    ) -> None:
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolio_ids = [p.id for p in result.scalars().all()]
        if not portfolio_ids:
            return

        asset_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.asset_type == AssetType.CRYPTO,
            )
        )
        assets = asset_result.scalars().all()
        aid_to_symbol = {str(a.id): a.symbol.upper() for a in assets}
        crypto_ids = [a.id for a in assets]
        if not crypto_ids:
            return

        trans_result = await db.execute(
            select(Transaction).where(Transaction.asset_id.in_(crypto_ids)).order_by(Transaction.executed_at.asc())
        )
        all_txs = list(trans_result.scalars().all())
        fifo: FifoLayers = fifo_replay.replay(
            fifo_replay.sort_transactions(all_txs),
            aid_to_symbol,
            TAX_MODE.config,
        ).fifo

        for order in orders:
            if order.action != "sell":
                continue
            estimated_gain = _estimate_order_gain(order, class_assets.get(order.category, []), fifo)
            order.estimated_gain = round(float(estimated_gain), 2)
            order.estimated_tax = round(max(0.0, float(estimated_gain)) * _PFU_RATE, 2)
