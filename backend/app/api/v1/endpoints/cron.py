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


@router.post("/invariants-check", dependencies=[Depends(verify_cron_token)])
async def cron_invariants_check() -> dict:
    """Run the financial invariants check across the live DB.

    Mirrors ``scripts/check_invariants.py`` but inside the API process, so a
    GitHub Actions cron can call it weekly and parse the JSON.
    """
    from sqlalchemy import text

    from app.core.database import engine

    invariants: dict[str, list[dict]] = {}
    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT a.id::text AS aid, a.symbol, a.exchange,
                       a.quantity AS stored,
                       COALESCE(SUM(CASE
                           WHEN t.transaction_type IN ('BUY','TRANSFER_IN','CONVERSION_IN','AIRDROP','STAKING_REWARD')
                               THEN t.quantity
                           WHEN t.transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT')
                               THEN -t.quantity ELSE 0
                       END), 0) AS computed
                FROM assets a
                LEFT JOIN transactions t ON t.asset_id = a.id
                WHERE a.asset_type != 'CROWDFUNDING'
                GROUP BY a.id, a.symbol, a.exchange, a.quantity
"""
                    )
                )
            )
            .mappings()
            .all()
        )
        invariants["holdings"] = [
            {
                "asset_id": r["aid"],
                "symbol": r["symbol"],
                "exchange": r["exchange"],
                "stored": float(r["stored"] or 0),
                "computed": float(r["computed"] or 0),
                "diff": float((r["stored"] or 0) - (r["computed"] or 0)),
            }
            for r in rows
            if abs(float((r["stored"] or 0) - (r["computed"] or 0))) > 1e-8
        ]

        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT t.id::text AS tx_id, a.symbol, t.currency, t.conversion_rate
                FROM transactions t JOIN assets a ON a.id = t.asset_id
                WHERE t.transaction_type IN ('BUY','SELL')
                  AND COALESCE(UPPER(t.currency),'EUR') <> 'EUR'
                  AND (t.conversion_rate IS NULL OR t.conversion_rate <= 0)
                LIMIT 20
            """
                    )
                )
            )
            .mappings()
            .all()
        )
        invariants["fx"] = [dict(r) for r in rows]

        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT user_id::text, (snapshot_date AT TIME ZONE 'UTC')::date AS day,
                       portfolio_id::text, COUNT(*) AS n
                FROM portfolio_snapshots
                GROUP BY user_id, day, portfolio_id
                HAVING COUNT(*) > 1
                LIMIT 10
            """
                    )
                )
            )
            .mappings()
            .all()
        )
        invariants["snapshots"] = [dict(r) for r in rows]

    total = sum(len(v) for v in invariants.values())
    return {
        "task": "invariants-check",
        "result": {
            "total_violations": total,
            "counts": {k: len(v) for k, v in invariants.items()},
            "details": {k: v[:50] for k, v in invariants.items()},
        },
    }
