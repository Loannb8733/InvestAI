"""Pytest configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator, Generator

# Set test env vars before any app import
os.environ.setdefault("SECRET_KEY", "testsecretkey_for_unit_tests_only_1234567890")
os.environ.setdefault("FERNET_KEY", "icQAqvAxUzGIr5HCiFPkDICQtKw_tIwRDbCnZW0HW6M=")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.user import User, UserRole

# Test database URL — only swap the database name in the path, never the username.
# (A naive str.replace of the DB name corrupts the user when they share a substring,
#  e.g. user "investai" + db "investai" -> both become "investai_test".)
_url_base, _url_db = settings.DATABASE_URL.rsplit("/", 1)
TEST_DATABASE_URL = f"{_url_base}/{_url_db}_test"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Create test session factory
TestSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter() -> AsyncGenerator[None, None]:
    """Flush slowapi's rate-limit buckets before every test.

    The limiter is backed by Redis (fixed-window, keyed by client IP), and that
    state outlives a single test. Without this reset, a test that deliberately
    exhausts a bucket (e.g. test_rate_limit) leaks 429s into later auth tests
    that share the same IP+window. Resetting up-front makes each test start with
    a fresh budget regardless of collection order.
    """
    from app.core.rate_limit import limiter

    try:
        limiter.reset()
    except Exception:
        # swallow_errors mirrors the limiter's own behaviour; a missing Redis
        # must never break the suite.
        pass
    yield


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # The app sets redirect_slashes=False (see app/main.py), so collection routes
    # declared with an empty path ("") are reachable ONLY at the no-slash URL
    # (e.g. "/api/v1/portfolios", not ".../portfolios/"). Tests must match that
    # exactly — there is no 307 to follow.
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user for testing."""
    user = User(
        email="admin@test.com",
        password_hash=hash_password("adminpassword"),
        role=UserRole.ADMIN,
        first_name="Admin",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    """Create a regular user for testing."""
    user = User(
        email="user@test.com",
        password_hash=hash_password("userpassword"),
        role=UserRole.USER,
        first_name="Regular",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
