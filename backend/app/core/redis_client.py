"""Redis client for caching predictions and fitted models."""

import hashlib
import hmac
import json
import logging
import pickle  # nosec B403 — ML model caching; HMAC-verified before deserialization
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

# HMAC key derived from SECRET_KEY for pickle integrity verification
_HMAC_KEY: bytes = settings.SECRET_KEY.encode() if isinstance(settings.SECRET_KEY, str) else settings.SECRET_KEY

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
    """Hash price data to detect staleness.

    Samples 10 evenly-spaced points plus extremes so that two series with
    identical length/first/last but different intermediate data produce
    different hashes.
    """
    if not prices:
        return "empty"
    n = len(prices)
    indices = sorted(set([0, n - 1] + [i * n // 10 for i in range(10)]))
    sample = [round(prices[i], 8) for i in indices if i < n]
    raw = f"{n}:{sum(sample):.8f}:{':'.join(str(s) for s in sample)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


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


async def cache_prediction(symbol: str, days: int, result: dict, ttl: int = 1800):
    """Cache prediction result (default 30min TTL)."""
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
# Pickle payloads are HMAC-signed on write and verified before deserialization
# to prevent arbitrary code execution if Redis is compromised.

_HMAC_SIG_LEN = 32  # SHA-256 digest length


def _sign_payload(data: bytes) -> bytes:
    """Prepend HMAC-SHA256 signature to pickle payload."""
    sig = hmac.new(_HMAC_KEY, data, hashlib.sha256).digest()
    return sig + data


def _verify_and_extract(data: bytes) -> Optional[bytes]:
    """Verify HMAC signature and return raw pickle payload, or None if invalid."""
    if len(data) <= _HMAC_SIG_LEN:
        return None
    sig = data[:_HMAC_SIG_LEN]
    payload = data[_HMAC_SIG_LEN:]
    expected = hmac.new(_HMAC_KEY, payload, hashlib.sha256).digest()
    if hmac.compare_digest(sig, expected):
        return payload
    return None


async def get_cached_model(symbol: str, model_name: str, data_hash: str) -> Optional[object]:
    """Get cached fitted model from Redis (HMAC-verified before deserialization)."""
    try:
        r = await _get_redis_bin()
        data = await r.get(f"model:{symbol}:{model_name}:{data_hash}")
        if data:
            payload = _verify_and_extract(data)
            if payload is None:
                logger.warning("HMAC verification failed for model %s:%s — discarding", symbol, model_name)
                return None
            return pickle.loads(payload)  # nosec B301 — HMAC-verified internal data
    except Exception as e:
        logger.debug("Redis model cache miss: %s", e)
    return None


async def cache_model(symbol: str, model_name: str, data_hash: str, model: object, ttl: int = 86400):
    """Cache fitted model in Redis with HMAC signature (default 24h TTL)."""
    try:
        r = await _get_redis_bin()
        raw = pickle.dumps(model)
        await r.setex(
            f"model:{symbol}:{model_name}:{data_hash}",
            ttl,
            _sign_payload(raw),
        )
    except Exception as e:
        logger.warning("Failed to cache model: %s", e)
