"""Valeur globale du portefeuille crypto au moment d'une cession (ligne 212 du 2086, BOI-RPPM-PVBMC-30-20 § 140).

Elle porte sur les actifs détenus avant la cession, actif cédé compris, tous supports confondus : l'actif cédé au
prix de la cession, les autres au cours historique en EUR du jour, ou du jour coté le plus proche dans les 7 jours
précédents. Un actif sans cours connu compte pour zéro.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset
from app.domains.transactions.cost_basis.context import aware
from app.domains.transactions.models import Transaction, TransactionType

ZERO = Decimal("0")
PRICE_FALLBACK_DAYS = 7

Holdings = dict[str, Decimal]
PriceCache = dict[date, dict[str, Decimal]]

_HOLDING_IN = (
    TransactionType.BUY,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.TRANSFER_IN,
    TransactionType.CONVERSION_IN,
)
_HOLDING_OUT = (TransactionType.SELL, TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT)


def _apply(holdings: Holdings, ttype: TransactionType, sym: str, qty: Decimal) -> None:
    if ttype in _HOLDING_IN:
        holdings[sym] += qty
    elif ttype in _HOLDING_OUT:
        holdings[sym] = max(ZERO, holdings[sym] - qty)


def holdings_before_sales(
    transactions: list[Transaction], asset_map: dict[uuid.UUID, Asset], until: datetime
) -> dict[uuid.UUID, Holdings]:
    """Quantités détenues par symbole juste avant chaque vente jusqu'à `until`, dans l'ordre du rejeu."""
    holdings: Holdings = defaultdict(lambda: ZERO)
    snapshots: dict[uuid.UUID, Holdings] = {}
    for tx in transactions:
        asset = asset_map.get(tx.asset_id)
        if not asset or not tx.executed_at:
            continue
        if tx.transaction_type == TransactionType.SELL and cast(datetime, aware(tx.executed_at)) <= until:
            snapshots[tx.id] = dict(holdings)
        _apply(holdings, tx.transaction_type, asset.symbol.upper(), Decimal(str(tx.quantity)))
    return snapshots


def portfolio_value(holdings: Holdings, sym: str, unit_price: Decimal, day_prices: dict[str, Decimal]) -> Decimal:
    """Valeur avant cession : l'actif cédé à `unit_price` (EUR), les autres au cours du jour."""
    value = ZERO
    for held_sym, held_qty in holdings.items():
        if held_qty > ZERO:
            value += held_qty * (unit_price if held_sym == sym else day_prices.get(held_sym, ZERO))
    return value


def _nearest(series: dict[date, Decimal], day: date) -> Decimal | None:
    for back in range(PRICE_FALLBACK_DAYS + 1):
        price = series.get(day - timedelta(days=back))
        if price is not None:
            return price
    return None


async def historical_prices(db: AsyncSession, symbols: Iterable[str], days: Iterable[date]) -> PriceCache:
    """Cours EUR de chaque symbole à chaque date, en une requête, avec repli sur les 7 jours précédents."""
    wanted = sorted(set(days))
    names = sorted(set(symbols))
    if not wanted or not names:
        return {day: {} for day in wanted}
    window = {day - timedelta(days=back) for day in wanted for back in range(PRICE_FALLBACK_DAYS + 1)}
    history = AssetPriceHistory
    rows = await db.execute(
        select(history.symbol, history.price_date, history.price_eur).where(
            history.symbol.in_(names), history.price_date.in_(window)
        )
    )
    series: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for symbol, price_date, price in rows.all():
        series[symbol.upper()][price_date] = Decimal(str(price))
    cache: PriceCache = {}
    for day in wanted:
        found = {sym: _nearest(prices, day) for sym, prices in series.items()}
        cache[day] = {sym: price for sym, price in found.items() if price is not None}
    return cache
