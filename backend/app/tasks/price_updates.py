"""Price update tasks.

After updating prices in the Redis cache, each task publishes price updates
to the Redis pub/sub channel ``price_updates`` so that the WebSocket endpoint
can broadcast them to connected clients in real time.
"""

import asyncio
import json
import logging
from typing import Dict, Set

from redis import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.services.price_service import PriceService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Initialize price service
price_service = PriceService()

# Redis pub/sub channel (must match the channel in websocket.py)
PRICE_UPDATES_CHANNEL = "price_updates"


def _get_sync_redis() -> Redis:
    """Get a synchronous Redis client for publishing from Celery workers."""
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
    )


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
        r = _get_sync_redis()
        payload = json.dumps(
            {
                "symbol": symbol.upper(),
                "price": price,
                "change_24h_percent": change_24h_percent,
                "asset_type": asset_type,
            }
        )
        r.publish(PRICE_UPDATES_CHANNEL, payload)
        r.close()
    except Exception as e:
        logger.debug("Failed to publish price update for %s: %s", symbol, e)


def run_async(coro):
    """Helper to run async code in sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create new loop if current is running
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


async def get_unique_symbols_by_type() -> Dict[str, Set[str]]:
    """Get unique asset symbols grouped by type from database."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(
                Asset.quantity > 0,
            )
            .distinct()
        )
        rows = result.all()

        symbols_by_type: Dict[str, Set[str]] = {
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


@celery_app.task(name="app.tasks.price_updates.update_crypto_prices")
def update_crypto_prices():
    """Update cryptocurrency prices from CoinGecko and publish to pub/sub."""
    logger.info("Starting crypto price update...")

    async def _update():
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

    return run_async(_update())


@celery_app.task(name="app.tasks.price_updates.update_stock_prices")
def update_stock_prices():
    """Update stock/ETF prices from Yahoo Finance and publish to pub/sub."""
    logger.info("Starting stock/ETF price update...")

    async def _update():
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

    return run_async(_update())


@celery_app.task(name="app.tasks.price_updates.update_exchange_rates")
def update_exchange_rates():
    """Update currency exchange rates."""
    logger.info("Starting exchange rate update...")

    async def _update():
        # Common currency pairs
        currencies = ["USD", "GBP", "CHF", "JPY", "CAD", "AUD"]
        base_currency = "EUR"

        updated_count = 0
        for currency in currencies:
            try:
                rate = await price_service.get_exchange_rate(base_currency, currency)
                if rate:
                    updated_count += 1
                    logger.debug(f"Updated {base_currency}/{currency}: {rate}")
            except Exception as e:
                logger.warning(f"Error fetching exchange rate {base_currency}/{currency}: {e}")

        logger.info(f"Exchange rate update complete: {updated_count} rates updated")
        return {"updated": updated_count, "base": base_currency, "currencies": currencies}

    return run_async(_update())


@celery_app.task(name="app.tasks.price_updates.update_all_prices")
def update_all_prices():
    """Update all asset prices (crypto, stocks, forex)."""
    logger.info("Starting full price update...")

    results = {
        "crypto": update_crypto_prices(),
        "stocks": update_stock_prices(),
        "forex": update_exchange_rates(),
    }

    logger.info(f"Full price update complete: {results}")
    return results
