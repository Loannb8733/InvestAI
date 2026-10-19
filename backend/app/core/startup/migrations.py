import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import settings
from app.core.db.metadata import metadata
from app.core.db.session import engine
from app.core.startup.multiplatform import fix_multiplatform_assets
from app.core.startup.rehash import rehash_transactions_internal_hash
from app.core.startup.transfer_mirrors import create_missing_transfer_mirrors

logger = logging.getLogger(__name__)

BOOT_LOCK_KEY = 4242424242


async def _close_quietly(conn: AsyncConnection) -> None:
    try:
        await conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to close boot advisory-lock connection: %s", exc)


@asynccontextmanager
async def boot_advisory_lock(key: int, lock_engine: AsyncEngine | None = None) -> AsyncIterator[None]:
    """Verrou consultatif Postgres sérialisant les démarrages concurrents ; n'empêche jamais le démarrage."""
    conn: AsyncConnection | None = None
    try:
        conn = await (lock_engine or engine).connect()
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
        logger.info("Acquired boot advisory lock")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Boot advisory lock unavailable, proceeding without it: %s", exc)
        if conn is not None:
            await _close_quietly(conn)
        conn = None
    try:
        yield
    finally:
        if conn is not None:
            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to release boot advisory lock (auto-released on disconnect): %s", exc)
            await _close_quietly(conn)


def run_alembic_upgrade() -> None:
    """Applique les migrations Alembic ; une base créée par create_all est d'abord marquée à la tête."""
    try:
        from alembic.config import Config

        from alembic import command

        config = Config("alembic.ini")
        config.attributes["configure_logger"] = False
        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.connect() as conn:
            if not inspect(conn).has_table("alembic_version"):
                logger.info("No alembic_version table, stamping to head")
                command.stamp(config, "head")
            elif (row := conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()) is None:
                logger.info("alembic_version empty, stamping to head")
                command.stamp(config, "head")
            else:
                logger.info("Alembic current revision: %s", row[0])
        sync_engine.dispose()
        command.upgrade(config, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alembic migration skipped or failed: %s", exc)


async def run_startup_migrations() -> None:
    """Migrations, création des tables manquantes et auto-réparations, sous verrou de démarrage."""
    async with boot_advisory_lock(BOOT_LOCK_KEY):
        run_alembic_upgrade()
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(
                text("ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS cash_balances JSON NOT NULL DEFAULT '{}'")
            )
        fix_multiplatform_assets()
        create_missing_transfer_mirrors()
        await rehash_transactions_internal_hash()
