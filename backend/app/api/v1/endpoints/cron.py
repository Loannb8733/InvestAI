"""Cron-triggered task endpoints.

The app has no Celery worker on the free tier, so scheduled jobs are triggered
by an external scheduler (GitHub Actions cron) POSTing to these endpoints. Each
runs the SAME business logic the Celery task would, inline in the web process.

Security: protected by a shared secret (X-Cron-Token == settings.CRON_SECRET).
When CRON_SECRET is empty the endpoints are disabled (503), so they stay inert
until explicitly configured.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_cron_token(x_cron_token: str = Header(default="")) -> None:
    """Reject unless the request carries the configured cron secret."""
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron endpoints are disabled (CRON_SECRET not configured).",
        )
    if not hmac.compare_digest(x_cron_token, settings.CRON_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cron token.")


@router.post("/sync-exchanges", dependencies=[Depends(verify_cron_token)])
async def cron_sync_exchanges() -> dict:
    """Hourly exchange sync for all active API keys (replaces the Celery beat job)."""
    from app.tasks.sync_exchanges import _sync_all_exchanges_async

    logger.info("Cron: sync-exchanges started")
    result = await _sync_all_exchanges_async()
    return {"task": "sync-exchanges", "result": result}


@router.post("/daily-snapshot", dependencies=[Depends(verify_cron_token)])
async def cron_daily_snapshot() -> dict:
    """Persist the daily portfolio snapshot for every user."""
    from app.tasks.snapshots import _create_all_snapshots_async

    logger.info("Cron: daily-snapshot started")
    result = await _create_all_snapshots_async()
    return {"task": "daily-snapshot", "result": result}


@router.post("/contrarian-refresh", dependencies=[Depends(verify_cron_token)])
async def cron_contrarian_refresh() -> dict:
    """Recompute the Fear & Greed contrarian backtest stats into Redis.

    The work is synchronous (httpx + pandas), so it runs in a thread to avoid
    blocking the event loop.
    """
    from app.tasks.contrarian_stats import refresh_contrarian_stats

    logger.info("Cron: contrarian-refresh started")
    result = await asyncio.to_thread(refresh_contrarian_stats)
    return {"task": "contrarian-refresh", "result": result}


@router.post("/regime-check", dependencies=[Depends(verify_cron_token)])
async def cron_regime_check() -> dict:
    """Detect global market-regime changes and notify users."""
    from app.services.regime_alert_service import regime_alert_service

    logger.info("Cron: regime-check started")
    result = await regime_alert_service.check_and_alert()
    return {"task": "regime-check", "result": result}
