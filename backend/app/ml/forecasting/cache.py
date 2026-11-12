import json
import logging
import time
from collections.abc import Callable
from typing import Any

import redis

from app.core.redis_client import redis_async_url, redis_client_kwargs
from app.ml.forecasting.types import ForecastResult

logger = logging.getLogger(__name__)

RESULT_TTL_S = 14400
LOCK_TTL_S = 120
POLL_ATTEMPTS = 30
_client: "redis.Redis[str] | None" = None


def sync_redis() -> "redis.Redis[str] | None":
    """Client Redis synchrone vérifié par PING à chaque accès ; None, et client oublié, si Redis ne répond pas."""
    global _client
    if _client is None:
        try:
            _client = redis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())
        except Exception as e:  # noqa: BLE001
            logger.warning("Sync Redis init failed (forecaster will run uncached): %s", e)
            return None
    try:
        if not _client.ping():
            _client = None
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Sync Redis PING failed, dropping singleton: %s", e)
        _client = None
        return None
    return _client


def _claim_lock(key: str) -> bool:
    r = sync_redis()
    if r is None:
        return True
    try:
        return bool(r.set(f"computing:{key}", "1", nx=True, ex=LOCK_TTL_S))
    except Exception:  # noqa: BLE001
        return True


def _release_lock(key: str) -> None:
    r = sync_redis()
    if r is None:
        return
    try:
        r.delete(f"computing:{key}")
    except Exception:  # noqa: BLE001
        logger.debug("Release of compute lock %s failed", key)


def _cached(key: str) -> ForecastResult | None:
    r = sync_redis()
    if r is None:
        return None
    try:
        data = r.get(key)
        if data:
            return ForecastResult(**json.loads(data))
    except Exception as e:  # noqa: BLE001
        logger.debug("Redis model result cache miss %s: %s", key, e)
    return None


def _store(key: str, result: ForecastResult) -> None:
    r = sync_redis()
    if r is None:
        return
    try:
        payload = json.dumps(
            {
                "dates": result.dates,
                "prices": result.prices,
                "confidence_low": result.confidence_low,
                "confidence_high": result.confidence_high,
                "trend": result.trend,
                "trend_strength": result.trend_strength,
                "model_used": result.model_used,
                "models_detail": result.models_detail,
                "explanations": result.explanations,
            },
            default=str,
        )
        r.setex(key, RESULT_TTL_S, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to cache model result %s: %s", key, e)


def run_cached(
    model_name: str, symbol: str | None, data_hash: str | None, days: int, run: Callable[[], ForecastResult]
) -> ForecastResult:
    """Résultat en cache 4 h par symbole, modèle, données et horizon ; un seul calcul à la fois pour une même clé."""
    if not (symbol and data_hash):
        return run()
    key = f"{symbol}:{model_name}:{data_hash}:{days}"
    cached = _cached(key)
    if cached is not None:
        logger.debug("Cache hit for %s", key)
        return cached
    if not _claim_lock(key):
        for _ in range(POLL_ATTEMPTS):
            time.sleep(1)
            cached = _cached(key)
            if cached is not None:
                return cached
    try:
        result = run()
        _store(key, result)
    finally:
        _release_lock(key)
    return result


def cached_hyperparams(symbol: str) -> dict[str, Any] | None:
    """Hyperparamètres Optuna rangés par la tâche de réglage, par modèle ; None sans entrée ni Redis."""
    r = sync_redis()
    if r is None:
        return None
    try:
        result = {}
        for model in ("xgboost", "prophet"):
            data = r.get(f"hparams:{symbol}:{model}")
            if data:
                result[model] = json.loads(data)
        return result if result else None
    except Exception as e:  # noqa: BLE001
        logger.debug("Failed to load cached hyperparams for %s: %s", symbol, e)
        return None
