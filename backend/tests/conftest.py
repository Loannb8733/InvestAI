"""Pytest configuration and fixtures."""

import os
import pathlib
from collections.abc import AsyncGenerator

# Set test env vars before any app import
os.environ.setdefault("SECRET_KEY", "testsecretkey_for_unit_tests_only_1234567890")
os.environ.setdefault("FERNET_KEY", "icQAqvAxUzGIr5HCiFPkDICQtKw_tIwRDbCnZW0HW6M=")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
if not os.environ.get("POSTGRES_DB", "investai").endswith("_test"):
    os.environ["POSTGRES_DB"] = os.environ.get("POSTGRES_DB", "investai") + "_test"
_redis_auth = f":{os.environ['REDIS_PASSWORD']}@" if os.environ.get("REDIS_PASSWORD") else ""
os.environ.setdefault(
    "REDIS_URL",
    f"redis://{_redis_auth}{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/15",
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db.metadata import metadata
from app.core.db.session import get_session
from app.core.redis_client import redis_async_url
from app.domains.identity.models import User, UserRole
from app.domains.identity.passwords import hash_password
from app.main import app
from tests.http_stubs import HttpStub
from tests.http_stubs import install as install_http_stub

# The application itself targets "<POSTGRES_DB>_test" (set above, before any app
# import): code that opens its own session never reads the development database.
TEST_DATABASE_URL = settings.DATABASE_URL
if not TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0].endswith("_test"):
    raise RuntimeError("Les tests suppriment le schéma de leur base : elle doit se nommer « …_test ».")

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

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


@pytest.fixture(autouse=True)
def _reset_fx_memory():
    from app.domains.market_data.fx.spot import spot_rates

    def reset() -> None:
        spot_rates.clear()

    reset()
    yield
    reset()


@pytest.fixture(autouse=True)
def _no_background_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun rafraîchissement d'historique hors du test : ni tâche sur la boucle, ni envoi au worker Celery.

    Sur la boucle, la tâche survit au test, interroge le réseau puis écrit dans la base pendant le
    ``drop_all`` du nettoyage : deadlock, et le test suivant hérite des lignes non supprimées.
    """
    from app.domains.market_data.history import tasks as history_tasks

    monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", True)
    monkeypatch.setattr(history_tasks.refresh_one, "delay", lambda *args, **kwargs: None)


@pytest.fixture
def live_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cotations fixes de tests.sample_portfolio à la place du réseau."""
    from app.domains.market_data.prices.service import price_feed
    from tests.sample_portfolio import fake_quote, fake_quotes

    monkeypatch.setattr(price_feed, "crypto", fake_quotes)
    monkeypatch.setattr(price_feed, "stocks", fake_quotes)
    monkeypatch.setattr(price_feed, "quote", fake_quote)


@pytest.fixture
def deterministic_forecaster(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remplace le forecaster du service de prédictions par son double déterministe (tests.forecaster_double)."""
    from app.domains.predictions.service import prediction_service
    from tests.forecaster_double import DeterministicForecaster

    monkeypatch.setattr(prediction_service, "forecaster", DeterministicForecaster())


@pytest.fixture
def http_stub(monkeypatch: pytest.MonkeyPatch) -> HttpStub:
    return install_http_stub(monkeypatch)


@pytest.fixture
def offline(http_stub: HttpStub) -> HttpStub:
    return http_stub


@pytest_asyncio.fixture
async def empty_test_redis() -> None:
    url = redis_async_url()
    assert url.endswith("/15"), f"refusing to flush a non-test Redis database: {url}"
    client = aioredis.from_url(url)
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Comme get_session, une requête qui aboutit est validée.

        Pas de rollback en cas d'erreur : il périmerait les objets des fixtures, partagés avec la session.
        """
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_session] = override_get_db

    # The app sets redirect_slashes=False (see app/main.py), so collection routes
    # declared with an empty path ("") are reachable ONLY at the no-slash URL
    # (e.g. "/api/v1/portfolios", not ".../portfolios/"). Tests must match that
    # exactly — there is no 307 to follow.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
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
