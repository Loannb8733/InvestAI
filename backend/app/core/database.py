"""Database configuration and session management."""

import logging
import os
import sys
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)


def _running_in_worker() -> bool:
    """Sommes-nous dans un worker Celery plutôt que dans le serveur web ?

    Le distinguo est structurel, pas cosmétique. FastAPI sert toutes ses requêtes
    dans UNE boucle asyncio : un pool de connexions y est un gain net. Une tâche
    Celery est synchrone et ouvre une boucle NEUVE à chaque exécution (cf.
    ``app.tasks.async_runner``) ; une connexion mise au pool par la tâche N reste
    attachée à la boucle N, désormais fermée. La tâche N+1 la récupère et lève
    « Task attached to a different loop » — de façon intermittente, puisque la
    connexion fautive est ensuite évincée. Reproduit le 2026-09-01 : 1re passe OK,
    2e en échec, 3e OK.

    ``DB_NULLPOOL`` permet de forcer le comportement sans dépendre de la détection.
    """
    forced = os.getenv("DB_NULLPOOL")
    if forced is not None:
        return forced.strip().lower() in {"1", "true", "yes", "on"}
    argv = " ".join(sys.argv[:2]).lower()
    return "celery" in argv


_IS_WORKER = _running_in_worker()

if _IS_WORKER:
    # NullPool : une connexion par usage, fermée derrière. Aucune ne survit à la
    # boucle qui l'a créée, donc aucune ne peut être reprise par la suivante.
    logger.info("Contexte worker détecté : engine en NullPool (aucune connexion mise en pool)")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        poolclass=NullPool,
    )
else:
    # Create async engine with proper pool configuration
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,  # Only log SQL in debug mode
        future=True,
        # Pool configuration for production
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Verify connections before use
        pool_timeout=30,  # Wait max 30s for a connection
    )

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    from fastapi import HTTPException

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except HTTPException:
            # HTTPException is normal flow control, not a DB error
            await session.rollback()
            raise
        except Exception as e:
            logger.error(f"Database error, rolling back: {type(e).__name__}: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
