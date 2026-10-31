"""Cours et taux de change utilisés par les métriques."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.service import FxService
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType

logger = logging.getLogger(__name__)

_CRYPTO_TIMEOUT = 5.0
_STOCK_TIMEOUT = 8.0


async def _crypto_unit_price(symbol: str, to_currency: str) -> float | None:
    quote = await price_feed.quote(symbol, "crypto", to_currency)
    return float(quote.price) if quote is not None else None


@dataclass
class RateResolver:
    """Taux vers la devise du portefeuille : change, puis cours crypto, puis 1 signalé comme périmé."""

    db: AsyncSession
    stale: bool = False

    async def rate(self, from_currency: str, to_currency: str) -> tuple[float, bool]:
        """Rend le taux et s'il est périmé, sans marquer la résolution."""
        quote = await FxService(FxRateRepository(self.db)).latest(from_currency, to_currency)
        if quote is not None:
            return float(quote.rate), quote.stale
        crypto_rate = await _crypto_unit_price(from_currency, to_currency)
        if crypto_rate is not None:
            return crypto_rate, False
        logger.warning("No FX rate for %s->%s; amounts kept unconverted", from_currency, to_currency)
        return 1.0, True

    async def tracked_rate(self, from_currency: str, to_currency: str) -> float:
        """Rend le taux et retient qu'un taux périmé a servi."""
        rate, stale = await self.rate(from_currency, to_currency)
        self.stale = self.stale or stale
        return rate


@dataclass
class MarketQuotes:
    """Cours courants et variations sur 24 h, par symbole."""

    prices: dict[str, Any] = field(default_factory=dict)
    changes: dict[str, Any] = field(default_factory=dict)

    def merge(self, quotes: dict[str, Any]) -> None:
        for symbol, quote in quotes.items():
            self.prices[symbol] = quote.price
            self.changes[symbol] = quote.change_percent_24h


async def fetch_market_quotes(assets: list[Asset], currency: str) -> MarketQuotes:
    """Cours en direct ; un délai dépassé retombe sur le cours enregistré de l'actif."""
    market = MarketQuotes()
    crypto = [asset.symbol for asset in assets if asset.asset_type == AssetType.CRYPTO]
    stocks = [asset.symbol for asset in assets if asset.asset_type in (AssetType.STOCK, AssetType.ETF)]
    if crypto:
        try:
            market.merge(await asyncio.wait_for(price_feed.crypto(crypto, currency), timeout=_CRYPTO_TIMEOUT))
        except TimeoutError:
            logger.warning("Crypto price fetch timed out, using DB fallback")
    if stocks:
        try:
            market.merge(await asyncio.wait_for(price_feed.stocks(stocks, currency), timeout=_STOCK_TIMEOUT))
        except TimeoutError:
            logger.warning("Stock price fetch timed out, using DB fallback")
    stored = {a.symbol.upper(): float(a.current_price) for a in assets if a.current_price and a.current_price > 0}
    for symbol, price in stored.items():
        if symbol not in market.prices:
            market.prices[symbol] = price
            market.changes.setdefault(symbol, 0.0)
    return market


async def fetch_stablecoin_prices(symbols: list[str], currency: str) -> dict[str, float]:
    """Cours de marché des stablecoins, pour détecter une perte de parité ; vide si le délai est dépassé."""
    if not symbols:
        return {}
    try:
        quotes = await asyncio.wait_for(price_feed.crypto(symbols, currency), timeout=_CRYPTO_TIMEOUT)
    except TimeoutError as exc:
        logger.debug("Live stablecoin price fetch failed, falling back to peg: %s", exc)
        return {}
    return {symbol: float(quote.price) for symbol, quote in quotes.items()}
