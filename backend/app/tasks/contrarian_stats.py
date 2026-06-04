"""Daily task: refresh the Fear & Greed contrarian backtest stats in Redis.

Recomputes BTC forward returns after extreme fear (F&G < 25) from the
latest public data and caches the result, so the conviction-buy strategy
always quotes up-to-date figures without any manual re-run.
"""

import json
import logging

from redis import Redis

from app.core.redis_client import CONTRARIAN_STATS_KEY, CONTRARIAN_STATS_TTL, redis_async_url, redis_ssl_kwargs
from app.services.contrarian_stats_service import compute_contrarian_stats
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_redis() -> Redis:
    return Redis.from_url(redis_async_url(), decode_responses=True, **redis_ssl_kwargs())


@celery_app.task(name="app.tasks.contrarian_stats.refresh_contrarian_stats")
def refresh_contrarian_stats() -> dict:
    """Recompute the contrarian backtest and cache it in Redis.

    On any failure, logs and leaves the previously cached value untouched
    (the cache has an 8-day TTL, so a few missed runs are harmless).
    """
    try:
        stats = compute_contrarian_stats()
    except Exception as e:
        logger.warning("Contrarian stats refresh failed, keeping cached value: %s", e)
        return {"status": "error", "error": str(e)}

    try:
        client = _get_redis()
        client.setex(CONTRARIAN_STATS_KEY, CONTRARIAN_STATS_TTL, json.dumps(stats))
    except Exception as e:
        logger.warning("Failed to cache contrarian stats: %s", e)
        return {"status": "computed_not_cached", "error": str(e)}

    logger.info(
        "Refreshed contrarian stats: n=%s, median_12m=%s%%, win=%s%%",
        stats["n"],
        stats["median_12m_pct"],
        stats["win_rate_12m_pct"],
    )
    return {"status": "ok", **stats}
