"""Single-flight guard on the dashboard cache prevents a stampede.

When N requests miss the in-memory cache at the same time (typically right after
the TTL expires), only ONE must recompute the full FIFO / value series; the rest
await that same result instead of hammering the DB and CPU with N recomputes.
"""

import asyncio

import pytest

from app.services import metrics_service as ms
from app.services.metrics_service import MetricsService


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

    with pytest.raises(ValueError, match="compute failed"):
        await asyncio.gather(*[svc.get_user_dashboard_metrics(None, "u2", "EUR", 30) for _ in range(3)])

    # No leaked in-flight future, nothing cached on failure.
    assert ("u2", 30, "EUR") not in ms._dashboard_inflight
    assert ("u2", 30, "EUR") not in ms._dashboard_cache
