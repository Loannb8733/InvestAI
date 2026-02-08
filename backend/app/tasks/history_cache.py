"""Task to pre-fetch and cache historical price data in Redis.

This avoids CoinGecko 429 errors on the Analytics page by fetching
historical data in the background with proper rate limiting.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set

from redis import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset, AssetType
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

REDIS_HISTORY_PREFIX = "hist:"
REDIS_HISTORY_TTL = 3600  # 1 hour


def _get_redis() -> Redis:
    return Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)


def _run_async(coro):
    """Always create a fresh event loop to avoid 'attached to a different loop' errors."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_all_crypto_symbols() -> list:
    """Get all unique crypto symbols from DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Asset.symbol, Asset.asset_type)
            .where(Asset.quantity > 0)
            .distinct()
        )
        return [
            (row[0].upper(), row[1].value)
            for row in result.all()
        ]


async def _fetch_and_cache_all():
    """Fetch 90-day history for all assets and store in Redis."""
    redis = _get_redis()
    assets = await _get_all_crypto_symbols()

    if not assets:
        logger.info("No assets to cache history for")
        return 0

    coingecko_key = getattr(settings, 'COINGECKO_API_KEY', None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)
    cached_count = 0

    try:
        for symbol, asset_type in assets:
            cache_key = f"{REDIS_HISTORY_PREFIX}{symbol}_90"

            # Skip if already cached and not expired
            existing = redis.get(cache_key)
            if existing:
                try:
                    data = json.loads(existing)
                    # Check if data is recent enough (< 50 min old)
                    if data.get("fetched_at", 0) > datetime.utcnow().timestamp() - 3000:
                        logger.debug("Skipping %s — still fresh in cache", symbol)
                        cached_count += 1
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass

            try:
                dates, prices = await fetcher.get_history(symbol, asset_type, days=90)
                if dates and prices:
                    payload = json.dumps({
                        "dates": [d.isoformat() for d in dates],
                        "prices": prices,
                        "fetched_at": datetime.utcnow().timestamp(),
                    })
                    redis.setex(cache_key, REDIS_HISTORY_TTL, payload)
                    cached_count += 1
                    logger.info("Cached %d data points for %s", len(prices), symbol)
                else:
                    logger.warning("No history data for %s", symbol)
            except Exception as e:
                logger.warning("Failed to fetch history for %s: %s", symbol, e)

            # Rate limit: 7s between requests — CoinGecko free tier is shared
            # with price_updates task, so we need generous spacing
            await asyncio.sleep(7.0)

    finally:
        await fetcher.close()

    logger.info("History cache complete: %d/%d assets cached", cached_count, len(assets))
    return cached_count


@celery_app.task(name="app.tasks.history_cache.cache_historical_data")
def cache_historical_data():
    """Celery task: fetch and cache historical data for all assets."""
    logger.info("Starting historical data cache task...")
    result = _run_async(_fetch_and_cache_all())
    return {"cached": result}


async def _cache_single(symbol: str, asset_type: str):
    """Fetch and cache history for a single asset."""
    redis = _get_redis()
    cache_key = f"{REDIS_HISTORY_PREFIX}{symbol.upper()}_90"

    # Skip if already cached
    if redis.get(cache_key):
        return True

    coingecko_key = getattr(settings, 'COINGECKO_API_KEY', None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)
    try:
        dates, prices = await fetcher.get_history(symbol, asset_type, days=90)
        if dates and prices:
            payload = json.dumps({
                "dates": [d.isoformat() for d in dates],
                "prices": prices,
                "fetched_at": datetime.utcnow().timestamp(),
            })
            redis.setex(cache_key, REDIS_HISTORY_TTL, payload)
            logger.info("Cached %d data points for %s (on-demand)", len(prices), symbol)
            return True
    except Exception as e:
        logger.warning("Failed to cache history for %s: %s", symbol, e)
    finally:
        await fetcher.close()
    return False


@celery_app.task(name="app.tasks.history_cache.cache_single_asset")
def cache_single_asset(symbol: str, asset_type: str):
    """Celery task: cache history for a single newly-added asset."""
    return _run_async(_cache_single(symbol, asset_type))


def get_cached_history(symbol: str, days: int = 90):
    """Read cached history from Redis. Returns (dates, prices) or ([], [])."""
    redis = _get_redis()
    cache_key = f"{REDIS_HISTORY_PREFIX}{symbol.upper()}_90"
    raw = redis.get(cache_key)
    if not raw:
        return [], []
    try:
        data = json.loads(raw)
        dates = [datetime.fromisoformat(d) for d in data["dates"]]
        prices = data["prices"]
        # Trim to requested days
        if days < 90 and len(dates) > days:
            return dates[-days:], prices[-days:]
        return dates, prices
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse cached history for %s: %s", symbol, e)
        return [], []
