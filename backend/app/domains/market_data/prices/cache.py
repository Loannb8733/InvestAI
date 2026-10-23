import json
import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.core.redis_client import _get_redis_txt
from app.domains.market_data.prices.quote import PriceQuote

logger = logging.getLogger(__name__)


def _key(kind: str, currency: str, symbol: str) -> str:
    return f"price:v3:{kind}:{currency}:{symbol}"


def _encode(quote: PriceQuote) -> str:
    return json.dumps(
        {
            "price": str(quote.price),
            "change_percent_24h": quote.change_percent_24h,
            "change_24h": quote.change_24h,
            "volume_24h": quote.volume_24h,
            "market_cap": quote.market_cap,
        }
    )


def _decode(raw: str) -> PriceQuote:
    data = json.loads(raw)
    return PriceQuote(
        price=Decimal(data["price"]),
        change_percent_24h=float(data["change_percent_24h"]),
        change_24h=float(data["change_24h"]),
        volume_24h=float(data["volume_24h"]),
        market_cap=float(data["market_cap"]),
    )


async def read_quotes(kind: str, currency: str, symbols: Sequence[str]) -> dict[str, PriceQuote]:
    """Cours en cache pour ``symbols``, en une seule commande Redis."""
    if not symbols:
        return {}
    try:
        raws = await (await _get_redis_txt()).mget([_key(kind, currency, s) for s in symbols])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lecture du cache de cours impossible : %s", exc)
        return {}
    found: dict[str, PriceQuote] = {}
    for symbol, raw in zip(symbols, raws, strict=True):
        if not raw:
            continue
        try:
            found[symbol] = _decode(str(raw))
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            logger.warning("Entrée de cache de cours illisible pour %s : %s", symbol, exc)
    return found


async def write_quotes(kind: str, currency: str, quotes: Mapping[str, PriceQuote], ttl_s: int) -> None:
    """Met ``quotes`` en cache pour ``ttl_s`` secondes, en un seul aller-retour Redis."""
    if not quotes:
        return
    try:
        async with (await _get_redis_txt()).pipeline(transaction=False) as pipe:
            for symbol, quote in quotes.items():
                pipe.set(_key(kind, currency, symbol), _encode(quote), ex=ttl_s)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Écriture du cache de cours impossible : %s", exc)
