"""Celery tasks for alert checking."""

import logging

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
