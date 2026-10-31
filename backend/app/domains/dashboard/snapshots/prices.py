"""Cours historiques de la série de valeur : mémoire du processus, puis base, jamais le réseau."""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.cache import put_bounded
from app.domains.market_data.history.reader import local_history
from app.domains.market_data.history.tasks import schedule_refresh
from app.domains.portfolio.classification import STABLECOIN_SYMBOLS

PriceSeries = dict[str, dict[str, float]]

_PRICE_CACHE_TTL = 1800
_MAX_PRICE_CACHE = 500

_price_cache: dict[tuple[str, int], tuple[float, dict[str, float]]] = {}


def _from_memory(symbols: dict[str, str], days: int) -> tuple[PriceSeries, dict[str, str]]:
    now = time.time()
    found: PriceSeries = {}
    missing: dict[str, str] = {}
    for symbol, asset_type in symbols.items():
        upper = symbol.upper()
        cached = _price_cache.get((upper, days))
        if cached is not None and now - cached[0] < _PRICE_CACHE_TTL:
            found[upper] = cached[1]
        else:
            missing[upper] = asset_type
    return found, missing


async def fetch_price_series(symbols: dict[str, str], days: int, db: AsyncSession) -> PriceSeries:
    """Cours par symbole et par date ; pas de série pour un stablecoin, un symbole absent est rafraîchi à part."""
    series, missing = _from_memory(symbols, days)
    quoted = {symbol: kind for symbol, kind in missing.items() if symbol not in STABLECOIN_SYMBOLS}
    series.update({symbol: {} for symbol in missing if symbol in STABLECOIN_SYMBOLS})
    if not missing:
        return series
    histories = await local_history(quoted, days + 5, db)
    for symbol, asset_type in quoted.items():
        history = histories[symbol]
        if history.prices:
            prices = {d.strftime("%Y-%m-%d"): p for d, p in zip(history.dates, history.prices, strict=True)}
            series[symbol] = prices
            put_bounded(_price_cache, (symbol, days), (time.time(), prices), _MAX_PRICE_CACHE)
            continue
        stale = _price_cache.get((symbol, days))
        if stale is not None:
            series[symbol] = stale[1]
        schedule_refresh(symbol, asset_type)
    return series
