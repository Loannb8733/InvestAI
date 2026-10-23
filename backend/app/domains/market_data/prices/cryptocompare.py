import logging
from collections.abc import Sequence
from decimal import Decimal

import httpx

from app.core.config import settings
from app.domains.market_data.prices.quote import PriceQuote

logger = logging.getLogger(__name__)

URL = "https://min-api.cryptocompare.com/data/pricemultifull"
TIMEOUT_S = 3.0


async def cryptocompare_quotes(symbols: Sequence[str], currency: str) -> dict[str, PriceQuote]:
    """Cours CryptoCompare ; rien sans clé configurée, l'API refusant toute requête anonyme."""
    if not settings.CRYPTOCOMPARE_API_KEY or not symbols:
        return {}
    ccy = currency.upper()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.get(
                URL,
                params={"fsyms": ",".join(symbols), "tsyms": ccy},
                headers={"authorization": f"Apikey {settings.CRYPTOCOMPARE_API_KEY}"},
            )
            response.raise_for_status()
            raw = response.json().get("RAW", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("CryptoCompare indisponible pour %s : %s", ",".join(symbols), exc)
        return {}
    found: dict[str, PriceQuote] = {}
    for symbol in symbols:
        row = raw.get(symbol, {}).get(ccy) or {}
        price = Decimal(str(row.get("PRICE") or 0))
        if price > 0:
            found[symbol] = PriceQuote(
                price=price,
                change_percent_24h=float(row.get("CHANGEPCT24HOUR") or 0),
                change_24h=float(row.get("CHANGE24HOUR") or 0),
                volume_24h=float(row.get("VOLUME24HOUR") or 0),
                market_cap=float(row.get("MKTCAP") or 0),
            )
    return found
