import asyncio
import logging
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

import httpx

from app.domains.market_data.fx.spot import spot_rates
from app.domains.market_data.prices.cache import read_quotes, write_quotes
from app.domains.market_data.prices.coingecko import CoinGecko
from app.domains.market_data.prices.cryptocompare import cryptocompare_quotes
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.stablecoins import peg_quote
from app.domains.market_data.prices.yahoo import yahoo_quote

logger = logging.getLogger(__name__)

CRYPTO_TTL_S = 120
STOCK_TTL_S = 300
YAHOO_TIMEOUT_S = 5.0
YAHOO_CONCURRENCY = 10
STOCK_TYPES = frozenset({"stock", "etf"})


def _unique(symbols: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(s.upper() for s in symbols if s))


class PriceService:
    """Façade unique des cours courants, tous exprimés dans la devise demandée.

    Un actif sans cours connu est absent du résultat : jamais de zéro ni de
    cours dans une autre devise présenté comme valide.
    """

    def __init__(self) -> None:
        self._coingecko = CoinGecko()
        self._yahoo = httpx.AsyncClient(timeout=YAHOO_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"})

    async def crypto(self, symbols: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
        """Cours des cryptomonnaies : cache, CoinGecko, CryptoCompare, puis ancrage des stablecoins."""
        wanted = _unique(symbols)
        ccy = currency.upper()
        found = await read_quotes("crypto", ccy, wanted)
        missing = [s for s in wanted if s not in found]
        if not missing:
            return found
        fetched = await self._coingecko.quotes(missing, ccy)
        fetched |= await cryptocompare_quotes([s for s in missing if s not in fetched], ccy)
        await write_quotes("crypto", ccy, fetched, CRYPTO_TTL_S)
        for symbol in missing:
            if symbol not in fetched and (pegged := await peg_quote(symbol, ccy)) is not None:
                fetched[symbol] = pegged
        return found | fetched

    async def stocks(self, tickers: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
        """Cours des actions et ETF, convertis depuis leur devise de cotation."""
        wanted = _unique(tickers)
        ccy = currency.upper()
        found = await read_quotes("stock", ccy, wanted)
        missing = [t for t in wanted if t not in found]
        slots = asyncio.Semaphore(YAHOO_CONCURRENCY)
        quotes = await asyncio.gather(*(self._stock(t, ccy, slots) for t in missing))
        fetched = {t: q for t, q in zip(missing, quotes, strict=True) if q is not None}
        await write_quotes("stock", ccy, fetched, STOCK_TTL_S)
        return found | fetched

    async def _stock(self, ticker: str, currency: str, slots: asyncio.Semaphore) -> PriceQuote | None:
        async with slots:
            listed = await yahoo_quote(self._yahoo, ticker)
        if listed is None:
            return None
        quote, quoted_in = listed
        rate = await spot_rates.get(quoted_in, currency)
        if rate is None:
            logger.warning("Cours de %s non converti : taux %s->%s indisponible", ticker, quoted_in, currency)
            return None
        return quote.converted(rate)

    async def quote(self, symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote | None:
        """Cours d'un actif coté ; None pour un type sans cotation (immobilier, crowdfunding…)."""
        if asset_type == "crypto":
            return (await self.crypto([symbol], currency)).get(symbol.upper())
        if asset_type in STOCK_TYPES:
            return (await self.stocks([symbol], currency)).get(symbol.upper())
        return None

    async def index_level(self, ticker: str) -> float | None:
        """Niveau d'un indice de marché (VIX…), sans conversion : ce n'est pas un prix."""
        listed = await yahoo_quote(self._yahoo, ticker)
        return float(listed[0].price) if listed is not None else None

    async def btc_dominance(self) -> float | None:
        """Part du bitcoin dans la capitalisation totale des cryptomonnaies, en pourcentage."""
        return await self._coingecko.btc_dominance()

    async def crypto_on(self, symbol: str, day: date, currency: str = "EUR") -> Decimal | None:
        """Cours d'une cryptomonnaie un jour passé."""
        return await self._coingecko.price_on(symbol.upper(), day, currency)


price_feed = PriceService()
