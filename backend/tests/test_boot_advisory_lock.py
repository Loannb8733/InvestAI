"""Boot advisory-lock tests (Ticket 3b automation).

The lifespan boot path isn't exercised by the API tests, so the advisory lock
that serializes concurrent boots had no coverage. These tests pin its real
behaviour against the test Postgres: it is mutually exclusive while held and
released afterwards, and it fails open when it cannot be acquired.
"""

import pytest
from sqlalchemy import text

from app.main import _BOOT_LOCK_KEY, _boot_advisory_lock
from tests.conftest import test_engine

# Use a dedicated key so a parallel real boot can never interfere with the test.
_TEST_KEY = _BOOT_LOCK_KEY + 1


@pytest.mark.asyncio
async def test_lock_is_mutually_exclusive_then_released():
    # While the lock is held, a *different* session cannot take it.
    async with _boot_advisory_lock(_TEST_KEY, lock_engine=test_engine):
        async with test_engine.connect() as probe:
            held = (await probe.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _TEST_KEY})).scalar()
        assert held is False, "lock should be held by the context manager"

    # After the block exits, the lock is free again.
    async with test_engine.connect() as probe:
        got = (await probe.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _TEST_KEY})).scalar()
        assert got is True, "lock should be released after the block"
        # Clean up the probe-held lock.
        await probe.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TEST_KEY})


@pytest.mark.asyncio
async def test_lock_fails_open_when_engine_unavailable():
    # A broken engine must not block startup: the body still runs (unlocked).
    class _BrokenEngine:
        async def connect(self):
            raise RuntimeError("simulated DB unavailable")

    ran = False
    async with _boot_advisory_lock(_TEST_KEY, lock_engine=_BrokenEngine()):
        ran = True
    assert ran is True, "body must run even when the lock cannot be acquired"
