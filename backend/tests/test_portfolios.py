"""Portfolio endpoint tests."""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User


@pytest.mark.asyncio
async def test_create_portfolio(client: AsyncClient, regular_user: User):
    """Test creating a portfolio."""
    token = create_access_token(subject=str(regular_user.id))
    response = await client.post(
        "/api/v1/portfolios/",
        json={"name": "Mon Portfolio", "description": "Test portfolio"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Mon Portfolio"
    assert data["description"] == "Test portfolio"
    assert data["user_id"] == str(regular_user.id)


@pytest.mark.asyncio
async def test_create_portfolio_no_auth(client: AsyncClient):
    """Test creating a portfolio without authentication."""
    response = await client.post(
        "/api/v1/portfolios/",
        json={"name": "Mon Portfolio"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_portfolios(client: AsyncClient, regular_user: User):
    """Test listing portfolios."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # Create a portfolio first
    await client.post(
        "/api/v1/portfolios/",
        json={"name": "Portfolio 1"},
        headers=headers,
    )

    response = await client.get("/api/v1/portfolios/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_update_portfolio(client: AsyncClient, regular_user: User):
    """Test updating a portfolio."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    create_resp = await client.post(
        "/api/v1/portfolios/",
        json={"name": "Old Name"},
        headers=headers,
    )
    portfolio_id = create_resp.json()["id"]

    # Update
    response = await client.patch(
        f"/api/v1/portfolios/{portfolio_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_portfolio(client: AsyncClient, regular_user: User):
    """Test soft-deleting a portfolio."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    create_resp = await client.post(
        "/api/v1/portfolios/",
        json={"name": "To Delete"},
        headers=headers,
    )
    portfolio_id = create_resp.json()["id"]

    # Delete
    response = await client.delete(
        f"/api/v1/portfolios/{portfolio_id}",
        headers=headers,
    )
    assert response.status_code == 204

    # Verify it's gone from list
    list_resp = await client.get("/api/v1/portfolios/", headers=headers)
    ids = [p["id"] for p in list_resp.json()]
    assert portfolio_id not in ids


@pytest.mark.asyncio
async def test_create_portfolio_validation(client: AsyncClient, regular_user: User):
    """Test portfolio creation validation."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # Empty name
    response = await client.post(
        "/api/v1/portfolios/",
        json={"name": ""},
        headers=headers,
    )
    assert response.status_code == 422
