"""Pytest configuration and fixtures."""

import asyncio
import os
import pathlib
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


def pytest_configure(config: pytest.Config) -> None:
    """Refuse un second pytest tant qu'un autre tourne sur la même base.

    La fixture ``db_session`` crée puis supprime tout le schéma **à chaque
    test**, sur la base ``investai_test`` partagée. Deux exécutions simultanées
    se détruisent donc mutuellement les tables, et le symptôme ne dit rien de la
    cause : on lit ``relation "users" does not exist`` et
    ``duplicate key ... pg_type_typname_nsp_index`` sur des tests parfaitement
    sains, en nombre variable d'une fois sur l'autre.

    C'est arrivé : une suite lancée en arrière-plan, un second pytest lancé
    par-dessus pour vérifier un fichier, et vingt-sept erreurs à expliquer qui
    n'avaient aucun rapport avec le code. Mieux vaut un refus immédiat et
    explicite qu'un diagnostic à refaire.

    Le verrou est posé pour la durée du processus et relâché à sa mort, y
    compris s'il est tué : ``flock`` est attaché au descripteur, non au fichier.
    """
    import fcntl
    import tempfile

    verrou = pathlib.Path(tempfile.gettempdir()) / "investai-pytest.lock"
    descripteur = verrou.open("w")
    try:
        fcntl.flock(descripteur, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        descripteur.close()
        raise pytest.UsageError(
            f"Un autre pytest tourne déjà (verrou {verrou}).\n"
            "Les deux partagent la base investai_test, dont le schéma est recréé à chaque "
            "test : les lancer ensemble produit des erreurs SQL sans rapport avec le code.\n"
            "Attendez la fin de l'exécution en cours, ou arrêtez-la."
        )
    descripteur.write(str(os.getpid()))
    descripteur.flush()
    # Référence gardée sur la configuration : refermer le descripteur relâcherait
    # le verrou, et le laisser au ramasse-miettes reviendrait au même.
    config._investai_verrou = descripteur


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
