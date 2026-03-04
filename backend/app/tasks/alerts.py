"""Celery tasks for alert checking."""

import logging
from datetime import date

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.services.alert_service import alert_service
from app.tasks.celery_app import celery_app
from app.tasks.price_updates import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.alerts.check_all_alerts")
def check_all_alerts():
    """Check all user alerts and trigger notifications."""
    logger.info("Starting alert check for all users...")

    async def _check_alerts():
        async with AsyncSessionLocal() as db:
            result = await alert_service.check_all_user_alerts(db)
            return result

    result = run_async(_check_alerts())
    logger.info(
        f"Alert check completed: {result['users_checked']} users checked, "
        f"{result['alerts_triggered']} alerts triggered"
    )
    return result


@celery_app.task(name="app.tasks.alerts.check_user_alerts")
def check_user_alerts(user_id: str):
    """Check alerts for a specific user."""
    logger.info(f"Checking alerts for user {user_id}...")

    async def _check_user():
        async with AsyncSessionLocal() as db:
            triggered = await alert_service.check_alerts(db, user_id)
            return [
                {
                    "alert_id": str(t.alert_id),
                    "alert_name": t.alert_name,
                    "symbol": t.symbol,
                    "message": t.message,
                }
                for t in triggered
            ]

    result = run_async(_check_user())
    logger.info(f"User {user_id}: {len(result)} alerts triggered")
    return result


@celery_app.task(name="app.tasks.alerts.seed_risk_weight_snapshots")
def seed_risk_weight_snapshots():
    """Pre-seed daily risk weight snapshots for all users' assets.

    Runs once daily at 00:05 UTC. Ensures that VOLATILITY_SPIKE alerts
    have a 'yesterday' baseline to compare against.
    """
    logger.info("Seeding daily risk weight snapshots...")

    async def _seed():
        from app.models.portfolio import Portfolio
        from app.models.user import User
        from app.services.metrics_service import metrics_service

        seeded = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User.id).where(User.is_active == True))
            user_ids = [str(uid) for uid in result.scalars().all()]

            for user_id in user_ids:
                try:
                    port_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == user_id))
                    portfolio_ids = [str(pid) for pid in port_result.scalars().all()]

                    today_str = date.today().isoformat()
                    for pid in portfolio_ids:
                        try:
                            data = await metrics_service.get_portfolio_metrics(db, pid)
                            for am in data.get("assets", []):
                                rw = am.get("risk_weight", 0.0)
                                await alert_service._cache_risk_weight(am["symbol"], today_str, rw)
                                seeded += 1
                        except Exception as e:
                            logger.debug("Skip portfolio %s: %s", pid, e)
                except Exception as e:
                    logger.error("Failed to seed risk weights for user %s: %s", user_id, e)

        return seeded

    count = run_async(_seed())
    logger.info("Risk weight seeding complete: %d snapshots cached", count)
    return {"seeded": count}
