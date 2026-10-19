"""Price update tasks.

After updating prices in the Redis cache, each task publishes price updates
to the Redis pub/sub channel ``price_updates`` so that the WebSocket endpoint
can broadcast them to connected clients in real time.
"""

import json
import logging

from redis import Redis
from sqlalchemy import select

from app.core.db.session import session_factory
from app.core.redis_client import redis_async_url, redis_client_kwargs
from app.models.asset import Asset, AssetType
from app.services.price_service import PriceService
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Initialize price service
price_service = PriceService()

# Redis pub/sub channel (must match the channel in websocket.py)
PRICE_UPDATES_CHANNEL = "price_updates"


def _get_sync_redis() -> Redis:
    """Get a synchronous Redis client for publishing from Celery workers.

    Built from REDIS_URL like every other client: REDIS_HOST/REDIS_PORT only
    exist in docker-compose. On Render (Upstash, TLS) they fell back to
    localhost:6379, so every publish failed at DEBUG level and no live price
    ever reached the WebSocket.
    """
    return Redis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())


# Client de publication, créé paresseusement dans le processus qui publie (après
# le fork du worker, jamais partagé entre processus). Une connexion neuve par
# cours coûtait CLIENT SETINFO ×2 + PUBLISH + fermeture : quatre commandes au
# lieu d'une, facturées une à une par Upstash.
_client_de_publication: Redis | None = None


def _publieur() -> Redis:
    global _client_de_publication
    if _client_de_publication is None:
        _client_de_publication = _get_sync_redis()
    return _client_de_publication


def publish_price_update(
    symbol: str,
    price: float,
    change_24h_percent: float,
    asset_type: str,
) -> None:
    """Publish a single price update to the Redis pub/sub channel.

    Args:
        symbol: Asset symbol (e.g. "BTC", "AAPL").
        price: Current price.
        change_24h_percent: 24-hour change percentage.
        asset_type: One of "crypto", "stock", "etf".
    """
    try:
        r = _publieur()
        payload = json.dumps(
            {
                "symbol": symbol.upper(),
                "price": price,
                "change_24h_percent": change_24h_percent,
                "asset_type": asset_type,
            }
        )
        r.publish(PRICE_UPDATES_CHANNEL, payload)
    except Exception as e:
        logger.debug("Failed to publish price update for %s: %s", symbol, e)


async def get_unique_symbols_by_type() -> dict[str, set[str]]:
    """Get unique asset symbols grouped by type from database."""
    async with session_factory() as db:
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(
                Asset.quantity > 0,
            )
            .distinct()
        )
        rows = result.all()

        symbols_by_type: dict[str, set[str]] = {
            "crypto": set(),
            "stock": set(),
            "etf": set(),
        }

        for symbol, asset_type in rows:
            if asset_type == AssetType.CRYPTO:
                symbols_by_type["crypto"].add(symbol.upper())
            elif asset_type == AssetType.STOCK:
                symbols_by_type["stock"].add(symbol.upper())
            elif asset_type == AssetType.ETF:
                symbols_by_type["etf"].add(symbol.upper())

        return symbols_by_type


# Corps asynchrones sortis des tâches : `update_all_prices` peut ainsi les
# enchaîner dans une seule boucle. Imbriqués, chaque tâche créait la sienne
# via `run_async`, et l'engine SQLAlchemy async gardait ses connexions liées
# à la première — d'où « Task attached to a different loop » (NEW-14).


async def _maj_crypto():
    symbols_by_type = await get_unique_symbols_by_type()
    crypto_symbols = list(symbols_by_type.get("crypto", set()))

    if not crypto_symbols:
        logger.info("No crypto assets to update")
        return {"updated": 0, "symbols": []}

    logger.info(f"Updating prices for {len(crypto_symbols)} crypto assets: {crypto_symbols[:10]}...")

    # Fetch prices in batches of 50 (CoinGecko limit)
    updated_count = 0
    batch_size = 50

    for i in range(0, len(crypto_symbols), batch_size):
        batch = crypto_symbols[i : i + batch_size]
        try:
            prices = await price_service.get_multiple_crypto_prices(batch)
            for symbol, price_data in prices.items():
                if price_data is not None:
                    updated_count += 1
                    # Publish to Redis pub/sub for WebSocket broadcast
                    publish_price_update(
                        symbol=symbol,
                        price=float(price_data.get("price", 0)),
                        change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                        asset_type="crypto",
                    )
            logger.info(f"Batch {i // batch_size + 1}: Updated {len(prices)} prices")
        except Exception as e:
            logger.error(f"Error fetching crypto prices batch: {e}")

    logger.info(f"Crypto price update complete: {updated_count} prices updated")
    return {"updated": updated_count, "symbols": crypto_symbols[:20]}


async def _maj_actions():
    symbols_by_type = await get_unique_symbols_by_type()
    stock_symbols = list(symbols_by_type.get("stock", set()))
    etf_symbols = list(symbols_by_type.get("etf", set()))

    if not stock_symbols and not etf_symbols:
        logger.info("No stock/ETF assets to update")
        return {"updated": 0, "symbols": []}

    all_symbols = stock_symbols + etf_symbols
    logger.info(f"Updating prices for {len(all_symbols)} stock/ETF assets...")

    updated_count = 0
    for symbol in stock_symbols:
        try:
            price_data = await price_service.get_stock_price(symbol)
            if price_data:
                updated_count += 1
                publish_price_update(
                    symbol=symbol,
                    price=float(price_data.get("price", 0)),
                    change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                    asset_type="stock",
                )
        except Exception as e:
            logger.warning(f"Error fetching price for {symbol}: {e}")

    for symbol in etf_symbols:
        try:
            price_data = await price_service.get_stock_price(symbol)
            if price_data:
                updated_count += 1
                publish_price_update(
                    symbol=symbol,
                    price=float(price_data.get("price", 0)),
                    change_24h_percent=float(price_data.get("change_percent_24h", 0)),
                    asset_type="etf",
                )
        except Exception as e:
            logger.warning(f"Error fetching price for {symbol}: {e}")

    logger.info(f"Stock/ETF price update complete: {updated_count} prices updated")
    return {"updated": updated_count, "symbols": all_symbols[:20]}


@celery_app.task(name="app.tasks.price_updates.update_crypto_prices")
def update_crypto_prices():
    """Update cryptocurrency prices from CoinGecko and publish to pub/sub."""
    logger.info("Starting crypto price update...")

    return run_async(_maj_crypto())


@celery_app.task(name="app.tasks.price_updates.update_stock_prices")
def update_stock_prices():
    """Update stock/ETF prices from Yahoo Finance and publish to pub/sub."""
    logger.info("Starting stock/ETF price update...")

    return run_async(_maj_actions())
