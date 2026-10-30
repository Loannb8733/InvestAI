import pytest
from httpx import AsyncClient, Response

from app.core.config import settings
from app.domains.identity.models import User
from app.domains.identity.tokens import REMEMBER_ME_DAYS

pytestmark = pytest.mark.usefixtures("empty_test_redis")

USER = {"email": "user@test.com", "password": "userpassword"}


def _refresh_cookie_lasts(response: Response, days: int) -> bool:
    cookies = response.headers.get_list("set-cookie")
    return any(c.startswith("refresh_token=") and f"Max-Age={days * 86400}" in c for c in cookies)


async def _refreshed_twice(client: AsyncClient, *, remember_me: bool) -> list[Response]:
    login = await client.post("/api/v1/auth/login", json={**USER, "remember_me": remember_me})
    token = login.json()["refresh_token"]
    responses = []
    for _ in range(2):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 200
        token = response.json()["refresh_token"]
        responses.append(response)
    return responses


async def test_remember_me_survives_every_refresh(client: AsyncClient, regular_user: User) -> None:
    for response in await _refreshed_twice(client, remember_me=True):
        assert _refresh_cookie_lasts(response, REMEMBER_ME_DAYS)


async def test_a_plain_session_stays_on_the_default_lifetime(client: AsyncClient, regular_user: User) -> None:
    for response in await _refreshed_twice(client, remember_me=False):
        assert _refresh_cookie_lasts(response, settings.REFRESH_TOKEN_EXPIRE_DAYS)
