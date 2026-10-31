"""Coût de revient d'un portefeuille, dérivé du rejeu FIFO de ses transactions."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics import repository
from app.domains.dashboard.metrics.quotes import RateResolver
from app.domains.portfolio.models import Asset
from app.domains.transactions.cost_basis.config import ReplayConfig, ReplayResult
from app.domains.transactions.cost_basis.layers import ZERO, FifoKey, Layer
from app.domains.transactions.cost_basis.replay import replay, sort_transactions
from app.domains.transactions.cost_basis.weighted_average import compute_cump_pru

logger = logging.getLogger(__name__)

_DIVIDEND_PREFIX = "__div__"


def asset_key(asset: Asset) -> FifoKey:
    """Clé (symbole, plateforme) d'un actif dans le rejeu."""
    return asset.symbol.upper(), (asset.exchange or "").strip()


@dataclass
class CostBook:
    """Ce que le rejeu apprend sur les actifs d'investissement d'un portefeuille."""

    seen_keys: set[FifoKey] = field(default_factory=set)
    invested: dict[str, Decimal] = field(default_factory=dict)
    buy_pra_by_symbol: dict[str, Decimal] = field(default_factory=dict)
    pru_by_key: dict[FifoKey, Decimal] = field(default_factory=dict)
    fees: dict[str, float] = field(default_factory=dict)
    first_dates: dict[str, datetime] = field(default_factory=dict)
    dividends: dict[FifoKey, Decimal] = field(default_factory=dict)
    foreign_layers: dict[FifoKey, list[Layer]] = field(default_factory=dict)


def _average_prices(
    assets: Sequence[Asset],
) -> tuple[dict[str, str], dict[str, str], dict[str, Decimal], dict[str, Decimal]]:
    symbols: dict[str, str] = {}
    exchanges: dict[str, str] = {}
    asset_prices: dict[str, Decimal] = {}
    symbol_prices: dict[str, Decimal] = {}
    for asset in assets:
        asset_id = str(asset.id)
        symbol = asset.symbol.upper()
        price = Decimal(str(asset.avg_buy_price)) if asset.avg_buy_price else ZERO
        symbols[asset_id] = symbol
        exchanges[asset_id] = (asset.exchange or "").strip()
        asset_prices[asset_id] = price
        if price > 0 and symbol_prices.get(symbol, ZERO) <= 0:
            symbol_prices[symbol] = price
    return symbols, exchanges, asset_prices, symbol_prices


def _log_btc_layers(replayed: ReplayResult) -> None:
    for key, layers in replayed.orphan_transit.items():
        quantity = sum(layer["qty"] for layer in layers)
        if key[0] == "BTC" and quantity > 0:
            cost = sum(layer["qty"] * layer["unit_cost"] for layer in layers)
            logger.warning(
                "[FIFO_DEBUG] BTC orphan transit %s qty=%s cost=%s layers=%s", key[1][:40], quantity, cost, len(layers)
            )
    for key, layers in replayed.fifo.items():
        if key[0] == "BTC":
            logger.debug(
                "[FIFO_DEBUG] BTC final %s qty=%s cost=%s layers=%s",
                key[1],
                sum(layer["qty"] for layer in layers),
                sum(layer["qty"] * layer["unit_cost"] for layer in layers),
                len(layers),
            )


async def _apply_pending_conversions(
    pending: list[tuple[Any, Decimal, str]],
    costs: dict[FifoKey, Decimal],
    dividends: dict[FifoKey, Decimal],
    rates: RateResolver,
    currency: str,
) -> None:
    for entry, amount, entry_currency in pending:
        converted = amount * Decimal(str(await rates.tracked_rate(entry_currency, currency)))
        if isinstance(entry, str) and entry.startswith(_DIVIDEND_PREFIX):
            symbol = entry[len(_DIVIDEND_PREFIX) :]
            for key in dividends:
                if key[0] == symbol:
                    dividends[key] += converted
                    break
        else:
            costs[entry] = costs.get(entry, ZERO) + converted


def _layer_totals(fifo: dict[FifoKey, list[Layer]]) -> tuple[dict[FifoKey, Decimal], dict[str, Decimal]]:
    costs: dict[FifoKey, Decimal] = {}
    paid_by_symbol: dict[str, Decimal] = {}
    for key, layers in fifo.items():
        costs[key] = sum((layer["qty"] * layer["unit_cost"] for layer in layers), ZERO)
        paid = sum((layer["qty"] for layer in layers if layer["is_paid"]), ZERO)
        paid_by_symbol[key[0]] = paid_by_symbol.get(key[0], ZERO) + paid
    return costs, paid_by_symbol


def _undiluted_prices(costs: dict[FifoKey, Decimal], paid_by_symbol: dict[str, Decimal]) -> dict[str, Decimal]:
    cost_by_symbol: dict[str, Decimal] = {}
    for key, cost in costs.items():
        cost_by_symbol[key[0]] = cost_by_symbol.get(key[0], ZERO) + cost
    return {
        symbol: cost / paid_by_symbol[symbol]
        for symbol, cost in cost_by_symbol.items()
        if paid_by_symbol.get(symbol, ZERO) > 0 and cost > 0
    }


def _invested_by_asset(
    assets: list[Asset], costs: dict[FifoKey, Decimal], seen_keys: set[FifoKey]
) -> dict[str, Decimal]:
    invested: dict[str, Decimal] = {}
    for asset in assets:
        key = asset_key(asset)
        cost = costs.get(key, ZERO)
        if cost > 0 or key in seen_keys:
            invested[str(asset.id)] = cost if cost > 0 else ZERO
    return invested


def _foreign_layers(fifo: dict[FifoKey, list[Layer]], currency: str) -> dict[FifoKey, list[Layer]]:
    foreign: dict[FifoKey, list[Layer]] = {}
    for key, layers in fifo.items():
        kept = [layer for layer in layers if layer["is_paid"] and layer["currency"] and layer["currency"] != currency]
        if kept:
            foreign[key] = kept
    return foreign


async def load_cost_book(
    db: AsyncSession, assets: list[Asset], currency: str, usd_to_target: float, rates: RateResolver
) -> CostBook:
    """Rejoue l'historique du portefeuille et rattache les coûts à chaque actif d'investissement."""
    if not assets:
        return CostBook()
    asset_ids = [asset.id for asset in assets]
    portfolio_id = assets[0].portfolio_id
    first_dates = await repository.first_transaction_dates(db, asset_ids)
    fees = await repository.fees_by_asset(db, asset_ids)
    transactions = sort_transactions(list(await repository.portfolio_transactions(db, portfolio_id)))
    every_asset = await repository.portfolio_assets(db, portfolio_id)
    symbols, exchanges, asset_prices, symbol_prices = _average_prices(every_asset)
    replayed = replay(
        transactions,
        symbols,
        ReplayConfig(portfolio_currency=currency, seed_stablecoin_layers=True),
        aid_to_avg_price=asset_prices,
        sym_avg_price=symbol_prices,
        usd_to_portfolio=usd_to_target,
    )
    _log_btc_layers(replayed)
    costs, paid_by_symbol = _layer_totals(replayed.fifo)
    seen_keys = set(replayed.fifo)
    await _apply_pending_conversions(
        replayed.pending_fee_conversions, costs, replayed.dividend_income, rates, currency.upper()
    )
    return CostBook(
        seen_keys=seen_keys,
        invested=_invested_by_asset(assets, costs, seen_keys),
        buy_pra_by_symbol=_undiluted_prices(costs, paid_by_symbol),
        pru_by_key=compute_cump_pru(transactions, symbols, exchanges),
        fees=fees,
        first_dates=first_dates,
        dividends=replayed.dividend_income,
        foreign_layers=_foreign_layers(replayed.fifo, currency.upper()),
    )
