"""Redis client for caching predictions and fitted models."""

import json
import hashlib
import pickle
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Async Redis client singleton
_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding=None,  # binary for pickle
            decode_responses=False,
        )
    return _redis


def _data_hash(prices: list) -> str:
    """Hash price data to detect staleness."""
    raw = f"{len(prices)}:{prices[-1] if prices else 0}:{prices[0] if prices else 0}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


async def get_cached_prediction(symbol: str, days: int) -> Optional[dict]:
    """Get cached prediction result."""
    try:
        r = await get_redis()
        data = await r.get(f"pred:{symbol}:{days}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis cache miss for prediction %s: %s", symbol, e)
    return None


async def cache_prediction(symbol: str, days: int, result: dict, ttl: int = 21600):
    """Cache prediction result (default 6h TTL)."""
    try:
        r = await get_redis()
        await r.setex(f"pred:{symbol}:{days}", ttl, json.dumps(result, default=str))
    except Exception as e:
        logger.warning("Failed to cache prediction: %s", e)


async def get_cached_model(symbol: str, model_name: str, data_hash: str) -> Optional[object]:
    """Get cached fitted model from Redis."""
    try:
        r = await get_redis()
        data = await r.get(f"model:{symbol}:{model_name}:{data_hash}")
        if data:
            return pickle.loads(data)
    except Exception as e:
        logger.debug("Redis model cache miss: %s", e)
    return None


async def cache_model(symbol: str, model_name: str, data_hash: str, model: object, ttl: int = 86400):
    """Cache fitted model in Redis (default 24h TTL)."""
    try:
        r = await get_redis()
        await r.setex(
            f"model:{symbol}:{model_name}:{data_hash}",
            ttl,
            pickle.dumps(model),
        )
    except Exception as e:
        logger.warning("Failed to cache model: %s", e)


async def get_cached_hyperparams(symbol: str, model_name: str) -> Optional[dict]:
    """Get cached optimal hyperparameters."""
    try:
        r = await get_redis()
        data = await r.get(f"hparams:{symbol}:{model_name}")
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


async def cache_hyperparams(symbol: str, model_name: str, params: dict, ttl: int = 604800):
    """Cache hyperparameters (default 7 days TTL)."""
    try:
        r = await get_redis()
        await r.setex(f"hparams:{symbol}:{model_name}", ttl, json.dumps(params))
    except Exception as e:
        logger.warning("Failed to cache hyperparams: %s", e)
