"""Celery task for regime mutation detection.

Runs every 12 hours, compares current BTC regime with last cached value,
and sends priority Telegram alerts on transition.
"""

import logging

from app.services.regime_alert_service import regime_alert_service
from app.tasks.celery_app import celery_app
from app.tasks.price_updates import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.regime_alerts.check_regime_mutation")
def check_regime_mutation():
    """Detect global market regime changes and notify users."""
    logger.info("Checking for regime mutation...")

    async def _check():
        return await regime_alert_service.check_and_alert()

    result = run_async(_check())

    status = result.get("status", "unknown")
    if status == "mutation":
        logger.info(
            "Regime mutation detected: %s → %s — %d users notified",
            result["old_regime"],
            result["new_regime"],
            result["users_notified"],
        )
    elif status == "seed":
        logger.info("First run — regime seeded: %s", result["regime"])
    elif status == "unchanged":
        logger.debug("Regime unchanged: %s", result["regime"])
    else:
        logger.warning("Regime check skipped: %s", result.get("reason", "unknown"))

    return result
