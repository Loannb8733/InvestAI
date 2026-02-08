"""Database configuration and session management."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

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
