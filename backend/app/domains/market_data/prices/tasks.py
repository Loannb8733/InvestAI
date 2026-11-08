import asyncio
import json
import logging
from typing import Any

from redis import Redis
from sqlalchemy import select

from app.core.db.session import session_factory
from app.core.redis_client import PRICE_UPDATES_CHANNEL, redis_async_url, redis_client_kwargs
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TRACKED_TYPES = (AssetType.CRYPTO, AssetType.STOCK, AssetType.ETF)
PUBLISHED_CURRENCY = "EUR"
CRYPTO_BATCH = 50
LISTED_SYMBOLS = 20

_publisher: Redis | None = None


def sync_redis() -> Redis:
    """Client Redis synchrone construit depuis REDIS_URL, comme tous les clients de l'application."""
    return Redis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())


def _shared_publisher() -> Redis:
    global _publisher
    if _publisher is None:
        _publisher = sync_redis()
    return _publisher


def publish_price_update(symbol: str, price: float, change_24h_percent: float, asset_type: str) -> bool:
    """Publie un cours en euros sur le canal relayé au websocket ; faux si la publication a échoué."""
    try:
        payload = json.dumps(
            {
                "symbol": symbol.upper(),
                "price": price,
                "change_24h_percent": change_24h_percent,
                "asset_type": asset_type,
                "currency": PUBLISHED_CURRENCY,
            }
        )
        _shared_publisher().publish(PRICE_UPDATES_CHANNEL, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to publish price update for %s: %s", symbol, exc)
        return False
    return True


async def held_symbols() -> dict[AssetType, list[str]]:
    """Symboles détenus en quantité positive, en majuscules et triés, pour chaque type d'actif coté."""
    async with session_factory() as db:
        rows = (await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())).all()
    symbols: dict[AssetType, set[str]] = {asset_type: set() for asset_type in TRACKED_TYPES}
    for symbol, asset_type in rows:
        if asset_type in symbols:
            symbols[asset_type].add(symbol.upper())
    return {asset_type: sorted(held) for asset_type, held in symbols.items()}


async def _publish(quotes: dict[str, PriceQuote], asset_types: dict[str, AssetType]) -> int:
    published = 0
    for symbol, quote in quotes.items():
        asset_type = asset_types[symbol].value
        if await asyncio.to_thread(
            publish_price_update, symbol, float(quote.price), quote.change_percent_24h, asset_type
        ):
            published += 1
    return published


async def publish_crypto_prices() -> dict[str, Any]:
    """Publie le cours de chaque crypto détenue, par lots de 50 symboles."""
    symbols = (await held_symbols())[AssetType.CRYPTO]
    if not symbols:
        logger.info("No crypto assets to update")
        return {"updated": 0, "symbols": []}
    logger.info("Updating prices for %d crypto assets: %s...", len(symbols), symbols[:10])
    updated = 0
    for start in range(0, len(symbols), CRYPTO_BATCH):
        batch = symbols[start : start + CRYPTO_BATCH]
        try:
            quotes = await price_feed.crypto(batch)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching crypto prices batch: %s", exc)
            continue
        updated += await _publish(quotes, dict.fromkeys(quotes, AssetType.CRYPTO))
        logger.info("Batch %d: Updated %d prices", start // CRYPTO_BATCH + 1, len(quotes))
    logger.info("Crypto price update complete: %d prices updated", updated)
    return {"updated": updated, "symbols": symbols[:LISTED_SYMBOLS]}


async def publish_stock_prices() -> dict[str, Any]:
    """Publie le cours de chaque action et de chaque ETF détenus, demandés en un seul appel."""
    held = await held_symbols()
    asset_types = {symbol: kind for kind in (AssetType.STOCK, AssetType.ETF) for symbol in held[kind]}
    if not asset_types:
        logger.info("No stock/ETF assets to update")
        return {"updated": 0, "symbols": []}
    listed = sorted(asset_types)
    logger.info("Updating prices for %d stock/ETF assets...", len(listed))
    try:
        quotes = await price_feed.stocks(listed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error fetching stock/ETF prices: %s", exc)
        quotes = {}
    updated = await _publish(quotes, asset_types)
    logger.info("Stock/ETF price update complete: %d prices updated", updated)
    return {"updated": updated, "symbols": listed[:LISTED_SYMBOLS]}


@celery_app.task(name="app.domains.market_data.prices.tasks.update_crypto_prices")  # type: ignore[untyped-decorator]
def update_crypto_prices() -> dict[str, Any]:
    """Tâche Celery planifiée : publie les cours des cryptos détenues."""
    logger.info("Starting crypto price update...")
    return run_async(publish_crypto_prices())


@celery_app.task(name="app.domains.market_data.prices.tasks.update_stock_prices")  # type: ignore[untyped-decorator]
def update_stock_prices() -> dict[str, Any]:
    """Tâche Celery planifiée : publie les cours des actions et ETF détenus."""
    logger.info("Starting stock/ETF price update...")
    return run_async(publish_stock_prices())
