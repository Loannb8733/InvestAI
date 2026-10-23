import logging
import os
import sys
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def is_worker_process() -> bool:
    """Indique si le processus est un worker Celery, qui ouvre une boucle asyncio par tâche."""
    forced = os.getenv("DB_NULLPOOL")
    if forced is not None:
        return forced.strip().lower() in _TRUE_VALUES
    return "celery" in " ".join(sys.argv[:2]).lower()


def _create_engine() -> AsyncEngine:
    if is_worker_process():
        logger.info("Contexte worker détecté : engine en NullPool")
        return create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, poolclass=NullPool)
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        pool_timeout=30,
    )


engine = _create_engine()

session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Ouvre une session par requête : commit si la requête aboutit, rollback sinon."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except (HTTPException, DomainError):
            await session.rollback()
            raise
        except Exception as exc:
            logger.error("Database error, rolling back: %s: %s", type(exc).__name__, exc)
            await session.rollback()
            raise
