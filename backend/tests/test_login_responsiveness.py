import asyncio
import time

import pytest
from httpx import AsyncClient

from app.domains.identity import auth_service
from app.domains.identity.models import User


async def test_a_login_does_not_freeze_other_requests(
    client: AsyncClient, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sur un dixième de processeur, bcrypt dure plusieurs secondes : il ne doit pas bloquer les autres requêtes."""
    verify = auth_service.verify_password

    def slow_verify(plain: str, hashed: str) -> bool:
        time.sleep(1.0)
        return verify(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", slow_verify)
    started = time.perf_counter()
    login = asyncio.create_task(
        client.post("/api/v1/auth/login", json={"email": "user@test.com", "password": "userpassword"})
    )
    await asyncio.sleep(0.3)
    assert (await client.get("/health")).status_code == 200
    health_done = time.perf_counter() - started
    assert (await login).status_code == 200
    assert health_done < 0.8
