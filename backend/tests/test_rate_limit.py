"""Rate limiting tests."""

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_login_rate_limit(client: AsyncClient, regular_user: User):
    """Test that login endpoint has rate limiting."""
    # Send multiple rapid login attempts
    responses = []
    for _ in range(10):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@test.com", "password": "wrongpassword"},
        )
        responses.append(resp.status_code)

    # At least some should be rate-limited (429)
    assert 429 in responses, "Rate limiting should block excessive login attempts"


@pytest.mark.asyncio
async def test_register_rate_limit(client: AsyncClient):
    """Test that register endpoint has rate limiting."""
    responses = []
    for i in range(8):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"test{i}@example.com",
                "password": "password123",
            },
        )
        responses.append(resp.status_code)

    # Register is limited to 3/minute
    assert 429 in responses, "Rate limiting should block excessive registrations"
