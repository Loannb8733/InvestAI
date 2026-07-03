"""Single-flight guard on the dashboard cache prevents a stampede.

When N requests miss the in-memory cache at the same time (typically right after
the TTL expires), only ONE must recompute the full FIFO / value series; the rest
await that same result instead of hammering the DB and CPU with N recomputes.
"""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.services import metrics_service as ms
from app.services import snapshot_service as ss
from app.services.metrics_service import MetricsService
from app.services.snapshot_service import SnapshotService


@contextmanager
def _isolate_l2_redis():
    """Neutralise the cross-worker L2 Redis layer so these tests exercise the
    in-process single-flight in isolation (L2 always misses, lock always granted,
    no writes that would poison a real Redis between runs)."""
    with (
        patch("app.core.redis_client.get_cached_dashboard", new=AsyncMock(return_value=None)),
        patch("app.core.redis_client.cache_dashboard", new=AsyncMock()),
        patch("app.core.redis_client.try_acquire_lock", new=AsyncMock(return_value=True)),
        patch("app.core.redis_client.release_lock", new=AsyncMock()),
    ):
        yield


@pytest.mark.asyncio
async def test_concurrent_misses_compute_once():
    ms._dashboard_cache.clear()
    ms._dashboard_inflight.clear()
    svc = MetricsService()

    calls = {"n": 0}

    async def slow_compute(db, user_id, currency, days):
        calls["n"] += 1
        await asyncio.sleep(0.05)  # hold long enough for the others to pile up
        return {"total_value": 42.0}

    svc._compute_user_dashboard_metrics = slow_compute

    with _isolate_l2_redis():
        results = await asyncio.gather(*[svc.get_user_dashboard_metrics(None, "u1", "EUR", 30) for _ in range(10)])

    assert calls["n"] == 1  # single-flight: computed exactly once for 10 concurrent misses
    assert all(r == {"total_value": 42.0} for r in results)
    # After completion the in-flight entry is cleared and the result is cached.
    assert ("u1", 30, "EUR") not in ms._dashboard_inflight
    assert ("u1", 30, "EUR") in ms._dashboard_cache


@pytest.mark.asyncio
async def test_failure_propagates_and_clears_inflight():
    ms._dashboard_cache.clear()
    ms._dashboard_inflight.clear()
    svc = MetricsService()

    async def boom(db, user_id, currency, days):
        await asyncio.sleep(0.01)
        raise ValueError("compute failed")

    svc._compute_user_dashboard_metrics = boom

    with _isolate_l2_redis(), pytest.raises(ValueError, match="compute failed"):
        await asyncio.gather(*[svc.get_user_dashboard_metrics(None, "u2", "EUR", 30) for _ in range(3)])

    # No leaked in-flight future, nothing cached on failure.
    assert ("u2", 30, "EUR") not in ms._dashboard_inflight
    assert ("u2", 30, "EUR") not in ms._dashboard_cache


@pytest.mark.asyncio
async def test_value_series_concurrent_misses_compute_once():
    ss._series_cache.clear()
    ss._series_inflight.clear()
    svc = SnapshotService()

    calls = {"n": 0}

    async def slow_compute(db, user_id, days, portfolio_id):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return [{"date": "2026-01-01", "value": 1.0}]

    svc._compute_portfolio_value_series = slow_compute

    results = await asyncio.gather(*[svc.build_portfolio_value_series(None, "u1", 30) for _ in range(10)])

    assert calls["n"] == 1  # single-flight: history replayed once for 10 concurrent misses
    assert all(r == [{"date": "2026-01-01", "value": 1.0}] for r in results)
    assert ("u1", 30) not in ss._series_inflight
    assert ("u1", 30) in ss._series_cache
