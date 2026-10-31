"""Métriques par position : valeur, gain, frais, durée de détention."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.finance_constants import annualized_return_pct
from app.domains.dashboard.metrics.ledger import CostBook, asset_key
from app.domains.dashboard.metrics.quotes import MarketQuotes, RateResolver
from app.domains.portfolio.models import Asset, AssetType
from app.domains.transactions.cost_basis.layers import ZERO, FifoKey

logger = logging.getLogger(__name__)

_DAYS_PER_YEAR = 365.25
_MIN_DAYS_FOR_ANNUALIZED = 7


def compute_asset_metrics(
    asset: Asset,
    current_price: Any = None,
    actual_invested: Decimal | None = None,
    buy_pra: Decimal | None = None,
    cump_pru: Decimal | None = None,
) -> dict[str, Any]:
    """Valeur et gain d'une position ; le coût FIFO prime sur le PRA du symbole, le PRU sert à l'affichage."""
    quantity = Decimal(str(asset.quantity))
    avg_buy_price = Decimal(str(asset.avg_buy_price))
    invested = Decimal(str(actual_invested)) if actual_invested is not None else None
    pra = Decimal(str(buy_pra)) if buy_pra is not None else None
    pru = Decimal(str(cump_pru)) if cump_pru is not None else None
    if pru is not None and pru > ZERO:
        avg_buy_price = pru
    elif invested is None and pra is not None and pra > 0:
        avg_buy_price = pra
    total_invested = invested if invested is not None else quantity * avg_buy_price
    price = Decimal(str(current_price)) if current_price is not None else None
    current_value = quantity * price if price is not None else total_invested
    gain_loss = current_value - total_invested if price is not None else ZERO
    has_gain = price is not None and total_invested > 0
    return {
        "quantity": float(quantity),
        "avg_buy_price": float(avg_buy_price),
        "total_invested": float(total_invested),
        "current_price": float(price) if price else None,
        "current_value": float(current_value),
        "gain_loss": float(gain_loss),
        "gain_loss_percent": float(gain_loss / total_invested * 100) if has_gain else 0.0,
    }


@dataclass
class ProjectTally:
    """Synthèse des biens valorisés à leur montant investi."""

    active: int = 0
    completed: int = 0
    total_invested: Decimal = ZERO
    projected_interest: Decimal = ZERO
    next_maturity: date | None = None

    def add(self, asset: Asset, amount: Decimal, status: str) -> None:
        if status == "completed":
            self.completed += 1
        else:
            self.active += 1
        self.total_invested += amount
        if status != "active":
            return
        rate = Decimal(str(asset.interest_rate)) if asset.interest_rate else ZERO
        if rate > 0:
            self.projected_interest += amount * rate / 100
        if asset.maturity_date and (self.next_maturity is None or asset.maturity_date < self.next_maturity):
            self.next_maturity = asset.maturity_date

    def summary(self) -> dict[str, Any]:
        return {
            "total_invested": float(self.total_invested),
            "active_projects": self.active,
            "completed_projects": self.completed,
            "projected_annual_interest": float(self.projected_interest),
            "next_maturity": self.next_maturity.isoformat() if self.next_maturity else None,
        }


@dataclass
class Positions:
    """Entrées par actif et totaux du portefeuille."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    total_value: Decimal = ZERO
    total_invested: Decimal = ZERO
    unpriced: set[str] = field(default_factory=set)
    projects: ProjectTally = field(default_factory=ProjectTally)


def _is_valued_at_cost(asset: Asset) -> bool:
    return asset.asset_type == AssetType.CROWDFUNDING or (
        asset.asset_type == AssetType.REAL_ESTATE and asset.invested_amount is not None
    )


def _project_metrics(asset: Asset, projects: ProjectTally) -> dict[str, Any]:
    amount = Decimal(str(asset.invested_amount))
    status = asset.project_status or "active"
    projects.add(asset, amount, status)
    completed = status == "completed"
    return {
        "quantity": float(asset.quantity),
        "avg_buy_price": float(amount),
        "total_invested": float(amount),
        "current_price": 0.0 if completed else float(amount),
        "current_value": 0.0 if completed else float(amount),
        "gain_loss": 0.0,
        "gain_loss_percent": 0.0,
    }


def _market_metrics(asset: Asset, book: CostBook, quotes: MarketQuotes) -> dict[str, Any]:
    key = asset_key(asset)
    metrics = compute_asset_metrics(
        asset,
        quotes.prices.get(key[0]),
        book.invested.get(str(asset.id)),
        book.buy_pra_by_symbol.get(key[0]) if key in book.seen_keys else None,
        book.pru_by_key.get(key),
    )
    if key[0] == "BTC":
        logger.debug(
            "[FIFO_DEBUG] BTC metrics_output exchange=%s qty=%s total_invested=%s current_value=%s gain_loss=%s",
            asset.exchange,
            asset.quantity,
            metrics["total_invested"],
            metrics["current_value"],
            metrics["gain_loss"],
        )
    return metrics


def _holding(first_date: datetime | None, metrics: dict[str, Any]) -> tuple[datetime | None, int | None, float | None]:
    if first_date is None:
        return None, None, None
    first = first_date.replace(tzinfo=UTC) if first_date.tzinfo is None else first_date
    days = (datetime.now(UTC) - first).days
    if days < _MIN_DAYS_FOR_ANNUALIZED or metrics["total_invested"] <= 0 or metrics["current_value"] <= 0:
        return first, days, None
    annualized = annualized_return_pct(
        float(metrics["total_invested"]), float(metrics["current_value"]), days / _DAYS_PER_YEAR
    )
    return first, days, round(annualized, 2)


def _breakeven(metrics: dict[str, Any], invested: Decimal | None, fees: float) -> float | None:
    quantity = metrics["quantity"]
    if quantity <= 0:
        return None
    cost = metrics["total_invested"] if invested is not None else metrics["total_invested"] + fees
    return round(float(cost / quantity), 2)


def _project_fields(asset: Asset) -> dict[str, Any]:
    return {
        "interest_rate": float(asset.interest_rate) if asset.interest_rate else None,
        "maturity_date": asset.maturity_date.isoformat() if asset.maturity_date else None,
        "project_status": asset.project_status,
        "invested_amount": float(asset.invested_amount) if asset.invested_amount else None,
    }


def _entry(
    asset: Asset, metrics: dict[str, Any], invested: Decimal | None, book: CostBook, change: Any
) -> dict[str, Any]:
    fees = book.fees.get(str(asset.id), 0.0)
    first, days, annualized = _holding(book.first_dates.get(str(asset.id)), metrics)
    entry = {
        "id": str(asset.id),
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type.value,
        "exchange": asset.exchange,
        "change_percent_24h": change,
        "total_fees": fees,
        "breakeven_price": _breakeven(metrics, invested, fees),
        "first_buy_date": first.isoformat() if first else None,
        "holding_days": days,
        "annualized_return": annualized,
        "dividend_income": float(book.dividends.get(asset_key(asset), ZERO)),
        **metrics,
    }
    return {**entry, **_project_fields(asset)} if _is_valued_at_cost(asset) else entry


def build_positions(
    assets: list[Asset], book: CostBook, quotes: MarketQuotes, *, include_zero: bool, min_value: float
) -> Positions:
    """Calcule chaque position ; hors `include_zero`, une poussière sans valeur ni coût est écartée."""
    positions = Positions()
    for asset in assets:
        valued_at_cost = _is_valued_at_cost(asset)
        invested = None if valued_at_cost else book.invested.get(str(asset.id))
        metrics = (
            _project_metrics(asset, positions.projects) if valued_at_cost else _market_metrics(asset, book, quotes)
        )
        if not valued_at_cost and quotes.prices.get(asset.symbol.upper()) is None:
            positions.unpriced.add(asset.symbol.upper())
        is_dust = metrics["current_value"] < min_value and metrics["total_invested"] < min_value
        if not valued_at_cost and not include_zero and is_dust:
            continue
        positions.total_value += Decimal(str(metrics["current_value"]))
        real_invested = book.invested.get(str(asset.id))
        positions.total_invested += (
            real_invested if real_invested is not None else Decimal(str(metrics["total_invested"]))
        )
        change = quotes.changes.get(asset.symbol.upper(), 0.0)
        positions.entries.append(_entry(asset, metrics, invested, book, change))
    return positions


async def _foreign_gains(
    book: CostBook, rates: RateResolver, target: str, known_rates: dict[str, float]
) -> dict[FifoKey, float]:
    gains: dict[FifoKey, float] = {}
    for key, layers in book.foreign_layers.items():
        total = 0.0
        for layer in layers:
            purchase_rate = float(layer["fx_rate"])
            currency = layer["currency"]
            if currency not in known_rates:
                known_rates[currency] = await _current_rate(rates, currency, target, purchase_rate)
            total += float(layer["qty"]) * float(layer["unit_cost_base"]) * (known_rates[currency] - purchase_rate)
        gains[key] = total
    return gains


async def _current_rate(rates: RateResolver, currency: str, target: str, purchase_rate: float) -> float:
    try:
        rate, _ = await rates.rate(currency, target)
    except Exception:  # noqa: BLE001
        logger.warning("Taux %s→%s indisponible — gain de change non décomposé", currency, target)
        return purchase_rate
    return rate


async def decorate_with_returns(
    positions: Positions, book: CostBook, rates: RateResolver, target: str, known_rates: dict[str, float]
) -> float:
    """Ajoute gain de change, gain hors change et rendement total à chaque entrée ; rend les dividendes cumulés."""
    gains = await _foreign_gains(book, rates, target, known_rates)
    total_dividends = 0.0
    for entry in positions.entries:
        key = (entry["symbol"].upper(), (entry.get("exchange") or "").strip())
        entry["fx_gain"] = round(gains.get(key, 0.0), 2)
        entry["asset_gain"] = round(entry["gain_loss"] - entry["fx_gain"], 2)
        entry["total_return"] = round(entry["gain_loss"] + entry["dividend_income"], 2)
        total_dividends += entry["dividend_income"]
    return total_dividends
