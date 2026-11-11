import time
from typing import Any

import pytest
from httpx import AsyncClient

from app.core import redis_client, redis_guard
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token

BLACKHOLE = "redis://10.255.255.1:6379/0"


async def test_a_network_failure_pauses_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []

    async def unreachable(self: Any, *args: Any, **options: Any) -> Any:
        calls.append(args)
        raise TimeoutError("Upstash injoignable")

    monkeypatch.setattr(redis_guard.aioredis.Redis, "execute_command", unreachable)
    client = redis_guard.GuardedRedis.from_url(BLACKHOLE)
    for _ in range(3):
        with pytest.raises((TimeoutError, redis_guard.RedisConnectionError)):
            await client.get("cle")
    assert len(calls) == 1
    monkeypatch.setattr(redis_guard, "_paused_until", time.monotonic() - 1)
    with pytest.raises(TimeoutError):
        await client.get("cle")
    assert len(calls) == 2


async def test_requests_stay_fast_while_redis_is_down(
    client: AsyncClient, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    unreachable = redis_guard.GuardedRedis.from_url(
        BLACKHOLE, decode_responses=True, socket_connect_timeout=1.0, socket_timeout=1.0
    )
    monkeypatch.setattr(redis_client, "_redis_txt", unreachable)
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    started = time.perf_counter()
    for _ in range(5):
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert time.perf_counter() - started < 1.0
