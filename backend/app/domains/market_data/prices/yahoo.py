import logging
from decimal import Decimal

import httpx

from app.domains.market_data.prices.quote import PriceQuote

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
SUBUNITS = {"GBp": ("GBP", Decimal(100)), "GBX": ("GBP", Decimal(100)), "ZAc": ("ZAR", Decimal(100))}


async def yahoo_quote(client: httpx.AsyncClient, ticker: str) -> tuple[PriceQuote, str] | None:
    """Cours d'une action ou d'un ETF et sa devise de cotation ; None sans cours positif."""
    try:
        response = await client.get(CHART_URL.format(ticker=ticker), params={"interval": "1d", "range": "5d"})
        response.raise_for_status()
        meta = response.json()["chart"]["result"][0]["meta"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo indisponible pour %s : %s", ticker, exc)
        return None
    raw_currency = str(meta.get("currency") or "USD")
    currency, divisor = SUBUNITS.get(raw_currency, (raw_currency.upper(), Decimal(1)))
    price = Decimal(str(meta.get("regularMarketPrice") or 0)) / divisor
    if price <= 0:
        return None
    previous = Decimal(str(meta.get("previousClose") or 0)) / divisor or price
    change = float(price - previous)
    quote = PriceQuote(
        price=price,
        change_percent_24h=change / float(previous) * 100,
        change_24h=change,
        volume_24h=float(meta.get("regularMarketVolume") or 0),
    )
    return quote, currency
