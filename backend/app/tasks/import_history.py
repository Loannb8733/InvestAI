"""Async import history task — runs exchange imports in background via Celery."""

import asyncio
import logging
import traceback

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async code in sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@celery_app.task(
    name="app.tasks.import_history.import_history_task",
    bind=True,
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540,  # 9 minutes soft limit
)
def import_history_task(self, api_key_id: str, user_id: str) -> dict:
    """Celery task: import full trade history from an exchange.

    Re-uses the existing _sync_single_exchange logic from sync_exchanges
    which handles trades, conversions, rewards, fiat orders, and balance
    reconciliation — all in a Celery-compatible async context.

    Returns a dict with status + import results or error.
    """
    self.update_state(state="PROGRESS", meta={"step": "importing"})

    try:
        from app.tasks.sync_exchanges import _sync_single_exchange

        result = run_async(_sync_single_exchange(api_key_id))

        if result.get("success"):
            return {
                "status": "completed",
                "synced": result.get("synced", 0),
                "message": "Import réussi",
            }
        else:
            return {
                "status": "failed",
                "error": result.get("error", "Unknown error"),
            }

    except Exception as e:
        logger.error(f"Import task error: {type(e).__name__}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return {
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }
