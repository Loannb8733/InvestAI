"""Métriques complètes d'un portefeuille."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics import repository
from app.domains.dashboard.metrics.cash import CashHoldings, ReferenceRates, value_fiat, value_stablecoins
from app.domains.dashboard.metrics.ledger import load_cost_book
from app.domains.dashboard.metrics.positions import Positions, build_positions, decorate_with_returns
from app.domains.dashboard.metrics.quotes import RateResolver, fetch_market_quotes
from app.domains.dashboard.metrics.volatility_weights import compute_risk_weights
from app.domains.portfolio.classification import is_cash_like, is_fiat, is_stablecoin
from app.domains.portfolio.models import Asset, AssetType
from app.domains.transactions.cost_basis.layers import ZERO

EMPTY_PORTFOLIO: dict[str, Any] = {
    "total_value": 0.0,
    "total_invested": 0.0,
    "unrealized_gain": 0.0,
    "total_dividend_income": 0.0,
    "assets_count": 0,
    "assets": [],
    "cash_from_stablecoins": 0.0,
    "stablecoins": [],
    "cash_from_fiat": 0.0,
    "fiat_assets": [],
}


def _without_estimated_dust(assets: Sequence[Asset], min_value: float) -> list[Asset]:
    threshold = Decimal(str(min_value))
    kept = []
    for asset in assets:
        average = Decimal(str(asset.avg_buy_price)) if asset.avg_buy_price else ZERO
        current = Decimal(str(asset.current_price)) if asset.current_price else ZERO
        price = average or current
        if price <= 0 or Decimal(str(asset.quantity)) * price >= threshold:
            kept.append(asset)
    return kept


async def _reference_rates(rates: RateResolver, target: str) -> ReferenceRates:
    usd = 1.0 if target == "USD" else await rates.tracked_rate("USD", target)
    eur = 1.0 if target == "EUR" else await rates.tracked_rate("EUR", target)
    return ReferenceRates(target=target, usd_to_target=usd, eur_to_target=eur)


async def _add_risk_weights(db: AsyncSession, positions: Positions) -> None:
    values: dict[str, float] = {}
    for entry in positions.entries:
        symbol = entry["symbol"].upper()
        values[symbol] = values.get(symbol, 0) + entry["current_value"]
    weights = await compute_risk_weights(db, values, float(positions.total_value))
    for entry in positions.entries:
        entry["risk_weight"] = weights.get(entry["symbol"].upper(), 0.0)


def _assemble(
    positions: Positions,
    stablecoins: CashHoldings,
    fiat: CashHoldings,
    total_dividends: float,
    forex_stale: bool,
) -> dict[str, Any]:
    projects = positions.projects
    result: dict[str, Any] = {
        "total_value": float(positions.total_value),
        "total_invested": float(positions.total_invested),
        "unrealized_gain": float(positions.total_value - positions.total_invested),
        "total_dividend_income": round(total_dividends, 2),
        "assets_count": len(positions.entries),
        "assets": positions.entries,
        "cash_from_stablecoins": float(stablecoins.total),
        "stablecoins": stablecoins.entries,
        "cash_from_fiat": float(fiat.total),
        "fiat_assets": fiat.entries,
        "available_liquidity": float(stablecoins.total + fiat.total),
        "forex_stale": forex_stale,
        "unpriced_symbols": sorted(positions.unpriced),
    }
    if projects.active > 0 or projects.completed > 0:
        result["crowdfunding_summary"] = projects.summary()
    return result


async def compute_portfolio_metrics(
    db: AsyncSession,
    portfolio_id: str,
    currency: str = "EUR",
    include_zero_quantity: bool = False,
    min_value_eur: float = 0.10,
) -> dict[str, Any]:
    """Positions, liquidités et totaux d'un portefeuille, valorisés dans `currency`."""
    stored = await repository.portfolio_assets(db, portfolio_id, include_zero=include_zero_quantity)
    assets = list(stored) if include_zero_quantity else _without_estimated_dust(stored, min_value_eur)
    if not assets:
        return {**EMPTY_PORTFOLIO, "assets": [], "stablecoins": [], "fiat_assets": []}
    investments = [a for a in assets if not is_cash_like(a.symbol) and a.asset_type != AssetType.CROWDFUNDING]
    target = currency.upper()
    resolver = RateResolver(db)
    reference = await _reference_rates(resolver, target)
    book = await load_cost_book(db, investments, currency, reference.usd_to_target, resolver)
    quotes = await fetch_market_quotes(investments, currency)
    positions = build_positions(investments, book, quotes, include_zero=include_zero_quantity, min_value=min_value_eur)
    known_rates = {"EUR": reference.eur_to_target, "USD": reference.usd_to_target, target: 1.0}
    total_dividends = await decorate_with_returns(positions, book, resolver, target, known_rates)
    stablecoins = await value_stablecoins(
        [a for a in assets if is_stablecoin(a.symbol)], reference, currency, min_value_eur
    )
    fiat = await value_fiat([a for a in assets if is_fiat(a.symbol)], reference)
    positions.entries.sort(key=lambda entry: entry["current_value"], reverse=True)
    await _add_risk_weights(db, positions)
    return _assemble(positions, stablecoins, fiat, total_dividends, resolver.stale)
