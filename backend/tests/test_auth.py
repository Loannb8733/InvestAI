"""Authentication tests."""

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, regular_user: User):
    """Test successful login."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "userpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, regular_user: User):
    """Test login with invalid password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_fails_closed_when_lockout_store_down(client: AsyncClient, regular_user: User, monkeypatch):
    """If the Redis lockout store is unreachable, login must 503 (fail-closed).

    Otherwise a Redis outage silently drops the brute-force throttle, letting an
    attacker hammer passwords with no lockout — even a valid password must not
    succeed while the throttle can't be enforced.
    """

    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.core.redis_client._get_redis_txt", _boom)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "userpassword"},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_access_token_without_fingerprint_rejected_in_production(
    client: AsyncClient, regular_user: User, monkeypatch
):
    """A production access token missing its `fp` claim is forged/tampered → 401.

    Every token the API issues carries a fingerprint; without this guard an
    fp-less token would skip binding validation entirely.
    """
    from app.core.config import settings
    from app.core.security import create_access_token

    token = create_access_token(subject=str(regular_user.id))  # no fingerprint
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)

    resp = await client.get("/api/v1/portfolios", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_access_token_without_fingerprint_allowed_outside_production(client: AsyncClient, regular_user: User):
    """Outside production the binding is not enforced (dev/test convenience)."""
    from app.core.security import create_access_token

    token = create_access_token(subject=str(regular_user.id))  # no fingerprint
    resp = await client.get("/api/v1/portfolios", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_access_token_revoked_after_logout(client: AsyncClient, regular_user: User):
    """Logging out blocklists the access token's jti so it stops working at once."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "userpassword"},
    )
    token = login.json()["access_token"]

    # Works before logout
    ok = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200

    # Logout revokes it (reads the access_token cookie set at login)
    await client.post("/api/v1/auth/logout")

    revoked = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_email(client: AsyncClient):
    """Test login with non-existent email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, regular_user: User):
    """Test getting current user info."""
    # First login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "userpassword"},
    )
    token = login_response.json()["access_token"]

    # Get current user
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@test.com"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, regular_user: User):
    """Test token refresh."""
    # First login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "userpassword"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Refresh token
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
