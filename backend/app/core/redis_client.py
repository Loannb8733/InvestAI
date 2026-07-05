"""Redis client for caching predictions and fitted models."""

import hashlib
import hmac
import json
import logging
import pickle  # nosec B403 — ML model caching; HMAC-verified before deserialization  # noqa: S403
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from app.core.config import settings


def redis_async_url() -> str:
    """Return REDIS_URL cleaned for redis.from_url() (sync ou asyncio).

    Strips the ssl_cert_reqs query param (kombu's CERT_* spellings cause
    parse errors in redis-py 5). We pass ssl_cert_reqs as a kwarg instead
    (see redis_ssl_kwargs). The raw settings.REDIS_URL is kept for
    Celery/kombu, which reads the param from the URL.
    """
    url = settings.REDIS_URL
    for value in ("CERT_REQUIRED", "CERT_OPTIONAL", "CERT_NONE", "required", "optional", "none"):
        for sep in (f"?ssl_cert_reqs={value}", f"&ssl_cert_reqs={value}"):
            url = url.replace(sep, "")
    if url.endswith("?"):
        url = url[:-1]
    return url


def redis_ssl_kwargs() -> Dict[str, Any]:
    """Return extra kwargs needed for TLS connections (Upstash).

    ssl_cert_reqs="required" : redis-py valide le certificat du broker
    (Upstash sert un certificat public de confiance — ne jamais désactiver
    la validation : CERT_NONE exposait au MITM).
    """
    if settings.REDIS_URL.startswith("rediss://"):
        return {"ssl_cert_reqs": "required"}
    return {}


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
            redis_async_url(),
            encoding=None,
            decode_responses=False,
            **redis_ssl_kwargs(),
        )
    return _redis_bin


async def _get_redis_txt() -> aioredis.Redis:
    """Text Redis client for JSON-serialized data."""
    global _redis_txt
    if _redis_txt is None:
        _redis_txt = aioredis.from_url(
            redis_async_url(),
            encoding="utf-8",
            decode_responses=True,
            **redis_ssl_kwargs(),
        )
    return _redis_txt


# Keep backward compat alias (binary client)
async def get_redis() -> aioredis.Redis:
    return await _get_redis_bin()


# ── Cross-worker single-flight lock ──────────────────────────────────
# A best-effort distributed lock so that, across multiple web workers, only one
# recomputes an expensive cached value at a time. Every path is fail-OPEN: if
# Redis is unreachable the caller behaves exactly as it did before (compute
# locally), never blocking on a lock it cannot reach.


async def try_acquire_lock(key: str, ttl: int = 20) -> bool:
    """Try to acquire ``key`` for ``ttl`` seconds. True = caller should compute.

    Returns True when the lock is freshly held OR when Redis is unreachable
    (fail-open: better to double-compute than to stall). Returns False only when
    Redis is up and another worker already holds the lock.
    """
    try:
        r = await _get_redis_txt()
        acquired = await r.set(f"lock:{key}", "1", nx=True, ex=max(ttl, 1))
        return bool(acquired)
    except Exception as e:  # noqa: BLE001 — degrade to "compute anyway"
        logger.debug("Lock acquire failed for %s (computing anyway): %s", key, e)
        return True


async def release_lock(key: str) -> None:
    """Release a lock acquired with try_acquire_lock (best-effort)."""
    try:
        r = await _get_redis_txt()
        await r.delete(f"lock:{key}")
    except Exception as e:  # noqa: BLE001
        logger.debug("Lock release failed for %s: %s", key, e)


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


# ── Forex rate cache ─────────────────────────────────────────────────

_FOREX_CACHE_TTL = 86400  # 24 hours
_FOREX_KEY_PREFIX = "forex:"


async def get_cached_forex_rate(from_ccy: str, to_ccy: str) -> Optional[dict]:
    """Get cached forex rate. Returns {"rate": float, "cached_at": ISO timestamp} or None."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"{_FOREX_KEY_PREFIX}{from_ccy}:{to_ccy}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis forex cache miss %s→%s: %s", from_ccy, to_ccy, e)
    return None


async def cache_forex_rate(from_ccy: str, to_ccy: str, rate: float) -> None:
    """Cache a forex rate with 24h TTL and timestamp."""
    try:
        from datetime import datetime, timezone

        r = await _get_redis_txt()
        payload = json.dumps(
            {
                "rate": rate,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await r.setex(f"{_FOREX_KEY_PREFIX}{from_ccy}:{to_ccy}", _FOREX_CACHE_TTL, payload)
    except Exception as e:
        logger.warning("Failed to cache forex rate %s→%s: %s", from_ccy, to_ccy, e)


# ── Dashboard response cache (use text client) ───────────────────────
# The dashboard aggregates many DB queries. We cache the full serialized
# response per (user, period, currency) with a short safety TTL. Any
# mutating request by the user invalidates all of their dashboard entries
# (see invalidate_dashboard_cache), so a cache hit is never stale.

_DASHBOARD_TTL = 300  # 5 minutes safety cap (invalidated eagerly on writes)
_DASHBOARD_KEY_PREFIX = "dashboard:"


def _dashboard_key(user_id: str, days: int, currency: str) -> str:
    return f"{_DASHBOARD_KEY_PREFIX}{user_id}:{days}:{currency}"


async def get_cached_dashboard(user_id: str, days: int, currency: str) -> Optional[dict]:
    """Get cached dashboard response dict, or None on miss/error."""
    try:
        r = await _get_redis_txt()
        data = await r.get(_dashboard_key(user_id, days, currency))
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis dashboard cache miss for %s: %s", user_id, e)
    return None


async def cache_dashboard(user_id: str, days: int, currency: str, payload: dict, ttl: int = _DASHBOARD_TTL) -> None:
    """Cache a dashboard response dict (JSON, default 5min TTL)."""
    try:
        r = await _get_redis_txt()
        await r.setex(
            _dashboard_key(user_id, days, currency),
            ttl,
            json.dumps(payload, default=str),
        )
    except Exception as e:
        logger.warning("Failed to cache dashboard for %s: %s", user_id, e)


async def invalidate_dashboard_cache(user_id: str) -> None:
    """Delete all cached dashboard entries for a user (all periods/currencies)."""
    try:
        r = await _get_redis_txt()
        pattern = f"{_DASHBOARD_KEY_PREFIX}{user_id}:*"
        keys = [key async for key in r.scan_iter(match=pattern, count=100)]
        if keys:
            await r.delete(*keys)
    except Exception as e:
        logger.warning("Failed to invalidate dashboard cache for %s: %s", user_id, e)


# ── Contrarian (Fear & Greed) backtest stats ─────────────────────────
# A daily Celery task recomputes the BTC-vs-Fear&Greed backtest and stores
# the result here. The conviction-buy strategy reads it to display live
# figures. TTL is generous (8 days) so a few failed refreshes still leave a
# usable, only-slightly-stale value rather than falling back to no numbers.

CONTRARIAN_STATS_KEY = "contrarian_stats:btc:fng"
CONTRARIAN_STATS_TTL = 691200  # 8 days


async def get_cached_contrarian_stats() -> Optional[dict]:
    """Get cached contrarian backtest stats dict, or None on miss/error."""
    try:
        r = await _get_redis_txt()
        data = await r.get(CONTRARIAN_STATS_KEY)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Redis contrarian-stats cache miss: %s", e)
    return None


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
    except Exception as exc:
        logger.debug("Redis hyperparams cache miss for %s:%s: %s", symbol, model_name, exc)
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
        await r.setex(
            f"ensemble:{symbol}:{data_hash}:{days}",
            ttl,
            json.dumps(result, default=str),
        )
    except Exception as e:
        logger.warning("Failed to cache ensemble: %s", e)


async def get_cached_reliability(symbol: str, days: int) -> Optional[dict]:
    """Get cached reliability scores."""
    try:
        r = await _get_redis_txt()
        data = await r.get(f"reliability:{symbol}:{days}")
        if data:
            return json.loads(data)
    except Exception as exc:
        logger.debug("Redis reliability cache miss for %s: %s", symbol, exc)
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
                logger.warning(
                    "HMAC verification failed for model %s:%s — discarding",
                    symbol,
                    model_name,
                )
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
