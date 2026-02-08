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
