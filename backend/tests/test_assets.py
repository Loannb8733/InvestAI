"""Asset endpoint tests."""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User


async def _create_portfolio(client: AsyncClient, token: str) -> str:
    """Helper to create a portfolio and return its ID."""
    resp = await client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_asset(client: AsyncClient, regular_user: User):
    """Test creating an asset."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    portfolio_id = await _create_portfolio(client, token)

    response = await client.post(
        "/api/v1/assets/",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "BTC",
            "name": "Bitcoin",
            "asset_type": "crypto",
            "quantity": "1.5",
            "avg_buy_price": "45000.00",
            "currency": "EUR",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["symbol"] == "BTC"
    assert data["asset_type"] == "crypto"


@pytest.mark.asyncio
async def test_create_duplicate_asset(client: AsyncClient, regular_user: User):
    """Test creating a duplicate asset in same portfolio."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    portfolio_id = await _create_portfolio(client, token)

    asset_data = {
        "portfolio_id": portfolio_id,
        "symbol": "ETH",
        "name": "Ethereum",
        "asset_type": "crypto",
        "quantity": "10",
        "avg_buy_price": "3000",
    }

    await client.post("/api/v1/assets/", json=asset_data, headers=headers)
    response = await client.post("/api/v1/assets/", json=asset_data, headers=headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_assets(client: AsyncClient, regular_user: User):
    """Test listing assets."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    portfolio_id = await _create_portfolio(client, token)

    # Create asset
    await client.post(
        "/api/v1/assets/",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "AAPL",
            "asset_type": "stock",
            "quantity": "50",
            "avg_buy_price": "150",
        },
        headers=headers,
    )

    response = await client.get("/api/v1/assets/", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_list_assets_filtered_by_portfolio(
    client: AsyncClient, regular_user: User
):
    """Test listing assets filtered by portfolio ID."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    portfolio_id = await _create_portfolio(client, token)

    response = await client.get(
        f"/api/v1/assets/?portfolio_id={portfolio_id}", headers=headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_asset(client: AsyncClient, regular_user: User):
    """Test updating an asset."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    portfolio_id = await _create_portfolio(client, token)

    create_resp = await client.post(
        "/api/v1/assets/",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "SOL",
            "asset_type": "crypto",
            "quantity": "100",
            "avg_buy_price": "20",
        },
        headers=headers,
    )
    asset_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/assets/{asset_id}",
        json={"quantity": "200"},
        headers=headers,
    )
    assert response.status_code == 200
    assert float(response.json()["quantity"]) == 200


@pytest.mark.asyncio
async def test_delete_asset(client: AsyncClient, regular_user: User):
    """Test soft-deleting an asset."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    portfolio_id = await _create_portfolio(client, token)

    create_resp = await client.post(
        "/api/v1/assets/",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "XRP",
            "asset_type": "crypto",
            "quantity": "1000",
            "avg_buy_price": "0.50",
        },
        headers=headers,
    )
    asset_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/assets/{asset_id}", headers=headers)
    assert response.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"/api/v1/assets/{asset_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_asset(client: AsyncClient, regular_user: User):
    """Test getting a nonexistent asset."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        "/api/v1/assets/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == 404
