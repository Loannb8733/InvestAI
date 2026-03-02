"""Redis client for caching predictions and fitted models."""

import hashlib
import json
import logging
import pickle  # nosec B403 — used for ML model caching (trusted internal data only)
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Two async Redis clients: one for binary (pickle), one for text (JSON)
_redis_bin: Optional[aioredis.Redis] = None
_redis_txt: Optional[aioredis.Redis] = None


async def _get_redis_bin() -> aioredis.Redis:
    """Binary Redis client for pickle-serialized objects (models)."""
    global _redis_bin
    if _redis_bin is None:
        _redis_bin = aioredis.from_url(
            settings.REDIS_URL,
            encoding=None,
            decode_responses=False,
        )
    return _redis_bin


async def _get_redis_txt() -> aioredis.Redis:
    """Text Redis client for JSON-serialized data."""
    global _redis_txt
    if _redis_txt is None:
        _redis_txt = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_txt


# Keep backward compat alias (binary client)
async def get_redis() -> aioredis.Redis:
    return await _get_redis_bin()


def _data_hash(prices: list) -> str:
    """Hash price data to detect staleness."""
    raw = f"{len(prices)}:{prices[-1] if prices else 0}:{prices[0] if prices else 0}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ── JSON-based caches (use text client) ──────────────────────────────


async def get_cached_prediction(symbol: str, days: int) -> Optional[dict]:
    """Get cached prediction result."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"pred:{symbol}:{days}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis cache miss for prediction %s: %s", symbol, e)
    return None


async def cache_prediction(symbol: str, days: int, result: dict, ttl: int = 21600):
    """Cache prediction result (default 6h TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(f"pred:{symbol}:{days}", ttl, json.dumps(result, default=str))
    except Exception as e:
        logger.warning("Failed to cache prediction: %s", e)


async def get_cached_hyperparams(symbol: str, model_name: str) -> Optional[dict]:
    """Get cached optimal hyperparameters."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"hparams:{symbol}:{model_name}")
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


async def cache_hyperparams(symbol: str, model_name: str, params: dict, ttl: int = 604800):
    """Cache hyperparameters (default 7 days TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(f"hparams:{symbol}:{model_name}", ttl, json.dumps(params))
    except Exception as e:
        logger.warning("Failed to cache hyperparams: %s", e)


async def get_cached_history(symbol: str, asset_type: str, days: int) -> Optional[dict]:
    """Get cached historical OHLCV data."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"hist:{symbol}:{asset_type}:{days}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis cache miss for history %s: %s", symbol, e)
    return None


async def cache_history(symbol: str, asset_type: str, days: int, result: dict, ttl: int = 3600):
    """Cache historical OHLCV data (default 1h TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(f"hist:{symbol}:{asset_type}:{days}", ttl, json.dumps(result, default=str))
    except Exception as e:
        logger.warning("Failed to cache history: %s", e)


async def get_cached_ensemble(symbol: str, data_hash: str, days: int) -> Optional[dict]:
    """Get cached ensemble forecast result."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"ensemble:{symbol}:{data_hash}:{days}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis cache miss for ensemble %s: %s", symbol, e)
    return None


async def cache_ensemble(symbol: str, data_hash: str, days: int, result: dict, ttl: int = 14400):
    """Cache ensemble forecast result (default 4h TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(f"ensemble:{symbol}:{data_hash}:{days}", ttl, json.dumps(result, default=str))
    except Exception as e:
        logger.warning("Failed to cache ensemble: %s", e)


async def get_cached_reliability(symbol: str, days: int) -> Optional[dict]:
    """Get cached reliability scores."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"reliability:{symbol}:{days}")
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


async def cache_reliability(symbol: str, days: int, result: dict, ttl: int = 86400):
    """Cache reliability scores (default 24h TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(f"reliability:{symbol}:{days}", ttl, json.dumps(result))
    except Exception as e:
        logger.warning("Failed to cache reliability: %s", e)


# ── Binary caches (use binary client for pickle) ─────────────────────
# Note: pickle is used ONLY for internally-generated ML model objects.
# No untrusted data is ever deserialized.


async def get_cached_model(symbol: str, model_name: str, data_hash: str) -> Optional[object]:
    """Get cached fitted model from Redis."""
    try:
        r = await _get_redis_bin()
        data = await r.get(f"model:{symbol}:{model_name}:{data_hash}")
        if data:
            return pickle.loads(data)  # nosec B301 — trusted internal data
    except Exception as e:
        logger.debug("Redis model cache miss: %s", e)
    return None


async def cache_model(symbol: str, model_name: str, data_hash: str, model: object, ttl: int = 86400):
    """Cache fitted model in Redis (default 24h TTL)."""
    try:
        r = await _get_redis_bin()
        await r.setex(
            f"model:{symbol}:{model_name}:{data_hash}",
            ttl,
            pickle.dumps(model),
        )
    except Exception as e:
        logger.warning("Failed to cache model: %s", e)
