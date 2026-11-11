import logging
import time
from typing import Any

import redis
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

PAUSE_S = 30.0
NETWORK_ERRORS = (RedisConnectionError, RedisTimeoutError, TimeoutError, OSError)

_paused_until = 0.0


def redis_paused() -> bool:
    """Vrai pendant les 30 s qui suivent une panne réseau de Redis : les appels échouent sans attendre."""
    return time.monotonic() < _paused_until


def pause_redis() -> None:
    """Met Redis en pause : chaque appel échoue aussitôt au lieu d'attendre le délai réseau."""
    global _paused_until
    if not redis_paused():
        logger.warning("Redis injoignable : appels suspendus %.0f s, l'application passe par ses replis", PAUSE_S)
    _paused_until = time.monotonic() + PAUSE_S


def _ensure_available() -> None:
    if redis_paused():
        raise RedisConnectionError("Redis en pause après une panne réseau")


class GuardedRedis(aioredis.Redis):
    """Client Redis asynchrone qui cesse d'attendre Redis après une panne réseau, le temps de la pause."""

    async def execute_command(self, *args: Any, **options: Any) -> Any:
        _ensure_available()
        try:
            return await super().execute_command(*args, **options)
        except NETWORK_ERRORS:
            pause_redis()
            raise

    def pipeline(self, transaction: bool = True, shard_hint: Any = None) -> Any:
        _ensure_available()
        return super().pipeline(transaction, shard_hint)


class GuardedSyncRedis(redis.Redis):
    """Client Redis synchrone, même pause après une panne réseau."""

    def execute_command(self, *args: Any, **options: Any) -> Any:
        _ensure_available()
        try:
            return super().execute_command(*args, **options)
        except NETWORK_ERRORS:
            pause_redis()
            raise
