import json
import logging
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.core.redis_client import _get_redis_txt
from app.domains.market_data.prices.quote import PriceQuote

logger = logging.getLogger(__name__)

_memory: dict[str, tuple[float, PriceQuote]] = {}


def _key(kind: str, currency: str, symbol: str) -> str:
    return f"price:v3:{kind}:{currency}:{symbol}"


def _remembered(key: str) -> PriceQuote | None:
    entry = _memory.get(key)
    if entry is None or entry[0] <= time.monotonic():
        _memory.pop(key, None)
        return None
    return entry[1]


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
    """Cours en cache pour ``symbols``, en une seule commande Redis ; Redis indisponible, ceux gardés en mémoire par
    ce processus."""
    if not symbols:
        return {}
    try:
        raws = await (await _get_redis_txt()).mget([_key(kind, currency, s) for s in symbols])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lecture du cache de cours impossible : %s", exc)
        remembered = {s: _remembered(_key(kind, currency, s)) for s in symbols}
        return {s: quote for s, quote in remembered.items() if quote is not None}
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
    """Met ``quotes`` en cache pour ``ttl_s`` secondes, en un seul aller-retour Redis, et en mémoire pour le cas où
    Redis serait indisponible à la lecture."""
    if not quotes:
        return
    expires = time.monotonic() + ttl_s
    _memory.update({_key(kind, currency, symbol): (expires, quote) for symbol, quote in quotes.items()})
    try:
        async with (await _get_redis_txt()).pipeline(transaction=False) as pipe:
            for symbol, quote in quotes.items():
                pipe.set(_key(kind, currency, symbol), _encode(quote), ex=ttl_s)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Écriture du cache de cours impossible : %s", exc)
