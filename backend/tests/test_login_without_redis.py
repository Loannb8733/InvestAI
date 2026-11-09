from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.errors import TooManyRequestsError, UnauthorizedError
from app.domains.identity import guards
from app.domains.identity.models import User


@pytest.fixture
def redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unreachable() -> None:
        raise TimeoutError("Upstash injoignable")

    monkeypatch.setattr(guards, "_get_redis_txt", unreachable)
    monkeypatch.setattr(guards, "_fallback", {})


@pytest.mark.usefixtures("redis_down")
async def test_login_works_while_redis_is_down(client: AsyncClient, regular_user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": "user@test.com", "password": "userpassword"})
    assert response.status_code == 200


@pytest.mark.usefixtures("redis_down")
async def test_lockout_still_applies_while_redis_is_down() -> None:
    user_id = uuid4()
    for _ in range(guards.LOCKOUT_THRESHOLD - 1):
        await guards.record_failure(user_id)
    await guards.ensure_not_locked(user_id)
    await guards.record_failure(user_id)
    with pytest.raises(TooManyRequestsError):
        await guards.ensure_not_locked(user_id)
    await guards.clear_failures(user_id)
    await guards.ensure_not_locked(user_id)


@pytest.mark.usefixtures("redis_down")
async def test_a_totp_code_cannot_be_replayed_while_redis_is_down() -> None:
    user_id = uuid4()
    await guards.ensure_totp_unused(user_id, "123456")
    await guards.mark_totp_used(user_id, "123456")
    with pytest.raises(UnauthorizedError):
        await guards.ensure_totp_unused(user_id, "123456")
