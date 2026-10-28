"""Daily task: refresh the Fear & Greed contrarian backtest stats in Redis.

Recomputes BTC forward returns after extreme fear (F&G < 25) from the
latest public data and caches the result, so the conviction-buy strategy
always quotes up-to-date figures without any manual re-run.
"""

import json
import logging

from redis import Redis

from app.core.errors import ServiceUnavailableError
from app.core.redis_client import CONTRARIAN_STATS_KEY, CONTRARIAN_STATS_TTL, redis_async_url, redis_client_kwargs
from app.services.contrarian_stats_service import compute_contrarian_stats
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_redis() -> Redis:
    return Redis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())


@celery_app.task(name="app.tasks.contrarian_stats.refresh_contrarian_stats")
def refresh_contrarian_stats() -> dict:
    """Recalcule le backtest contrarian et le met en cache dans Redis ; en échec, lève ``ServiceUnavailableError`` et
    laisse la valeur en cache, valable 8 jours."""
    try:
        stats = compute_contrarian_stats()
        _get_redis().setex(CONTRARIAN_STATS_KEY, CONTRARIAN_STATS_TTL, json.dumps(stats))
    except Exception as exc:
        raise ServiceUnavailableError(f"Statistiques contrarian non rafraîchies : {exc}") from exc

    logger.info(
        "Refreshed contrarian stats: n=%s, median_12m=%s%%, win=%s%%",
        stats["n"],
        stats["median_12m_pct"],
        stats["win_rate_12m_pct"],
    )
    return {"status": "ok", **stats}
