import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.db.session import engine
from app.core.startup.migrations import run_startup_migrations

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()


async def _startup_backfill() -> None:
    try:
        from app.domains.market_data.history.tasks import refresh_all

        count = await refresh_all()
        logger.info("Startup price backfill complete: %d assets cached", count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup price backfill failed: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Démarrage : migrations sous verrou puis préchargement des prix en tâche de fond."""
    logger.info("Starting %s (env=%s, debug=%s)", settings.APP_NAME, settings.APP_ENV, settings.DEBUG)
    await run_startup_migrations()
    task = asyncio.create_task(_startup_backfill())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info("Triggered startup price backfill (background)")
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
    await engine.dispose()
