"""Dashboard metrics must share results across workers via Redis (L2), not just
the per-worker in-memory cache — with a cross-worker lock so simultaneous misses
don't all recompute. Every Redis path is fail-open.
"""

from unittest.mock import AsyncMock, patch

import pytest

import app.services.metrics_service as ms
from app.services.metrics_service import MetricsService, invalidate_dashboard_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    ms._dashboard_cache.clear()
    ms._dashboard_inflight.clear()
    yield
    ms._dashboard_cache.clear()
    ms._dashboard_inflight.clear()


@pytest.mark.asyncio
async def test_shared_redis_hit_short_circuits_compute():
    svc = MetricsService()
    shared = {"total_value": 42.0}
    with (
        patch("app.core.redis_client.get_cached_dashboard", new=AsyncMock(return_value=shared)),
        patch.object(MetricsService, "_compute_user_dashboard_metrics", new=AsyncMock()) as comp,
    ):
        out = await svc.get_user_dashboard_metrics(db=None, user_id="u1", days=30)
    assert out == shared
    comp.assert_not_called()


@pytest.mark.asyncio
async def test_miss_computes_under_lock_and_writes_shared_cache():
    svc = MetricsService()
    result = {"total_value": 7.0}
    with (
        patch("app.core.redis_client.get_cached_dashboard", new=AsyncMock(return_value=None)),
        patch("app.core.redis_client.cache_dashboard", new=AsyncMock()) as setc,
        patch("app.core.redis_client.try_acquire_lock", new=AsyncMock(return_value=True)),
        patch("app.core.redis_client.release_lock", new=AsyncMock()) as rel,
        patch.object(MetricsService, "_compute_user_dashboard_metrics", new=AsyncMock(return_value=result)) as comp,
    ):
        out = await svc.get_user_dashboard_metrics(db=None, user_id="u2", days=30)
    assert out == result
    comp.assert_awaited_once()
    setc.assert_awaited_once()
    rel.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_loser_reuses_peer_result_without_recomputing():
    svc = MetricsService()
    peer = {"total_value": 99.0}
    # L2 check misses (None); after losing the lock the poll finds the peer's result.
    gets = AsyncMock(side_effect=[None, peer])
    with (
        patch("app.core.redis_client.get_cached_dashboard", new=gets),
        patch("app.core.redis_client.cache_dashboard", new=AsyncMock()),
        patch("app.core.redis_client.try_acquire_lock", new=AsyncMock(return_value=False)),
        patch("app.core.redis_client.release_lock", new=AsyncMock()),
        patch.object(MetricsService, "_compute_user_dashboard_metrics", new=AsyncMock()) as comp,
    ):
        out = await svc.get_user_dashboard_metrics(db=None, user_id="u3", days=30)
    assert out == peer
    comp.assert_not_called()


def test_invalidate_is_safe_without_a_running_loop():
    # Sync context (no event loop): clears L1 and swallows the Redis scheduling.
    ms._dashboard_cache[("u4", 30, "EUR")] = (0.0, {"total_value": 1.0})
    invalidate_dashboard_cache("u4")
    assert not any(k[0] == "u4" for k in ms._dashboard_cache)
