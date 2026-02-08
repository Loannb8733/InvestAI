"""Transaction endpoint tests."""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User


async def _setup_asset(client: AsyncClient, token: str) -> tuple[str, str]:
    """Helper to create a portfolio and asset, returning (portfolio_id, asset_id)."""
    headers = {"Authorization": f"Bearer {token}"}

    portfolio_resp = await client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio"},
        headers=headers,
    )
    portfolio_id = portfolio_resp.json()["id"]

    asset_resp = await client.post(
        "/api/v1/assets/",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "BTC",
            "asset_type": "crypto",
            "quantity": "1",
            "avg_buy_price": "40000",
        },
        headers=headers,
    )
    asset_id = asset_resp.json()["id"]
    return portfolio_id, asset_id


@pytest.mark.asyncio
async def test_create_transaction(client: AsyncClient, regular_user: User):
    """Test creating a buy transaction."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    _, asset_id = await _setup_asset(client, token)

    response = await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": asset_id,
            "transaction_type": "buy",
            "quantity": "0.5",
            "price": "42000",
            "fee": "10",
            "currency": "EUR",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["transaction_type"] == "buy"
    assert data["asset_id"] == asset_id


@pytest.mark.asyncio
async def test_create_sell_transaction(client: AsyncClient, regular_user: User):
    """Test creating a sell transaction."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    _, asset_id = await _setup_asset(client, token)

    response = await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": asset_id,
            "transaction_type": "sell",
            "quantity": "0.25",
            "price": "50000",
            "fee": "5",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["transaction_type"] == "sell"


@pytest.mark.asyncio
async def test_list_transactions(client: AsyncClient, regular_user: User):
    """Test listing transactions."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    _, asset_id = await _setup_asset(client, token)

    # Create a transaction
    await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": asset_id,
            "transaction_type": "buy",
            "quantity": "1",
            "price": "40000",
        },
        headers=headers,
    )

    response = await client.get("/api/v1/transactions/", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_delete_transaction(client: AsyncClient, regular_user: User):
    """Test soft-deleting a transaction."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    _, asset_id = await _setup_asset(client, token)

    create_resp = await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": asset_id,
            "transaction_type": "buy",
            "quantity": "1",
            "price": "40000",
        },
        headers=headers,
    )
    tx_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/transactions/{tx_id}", headers=headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_transaction_no_auth(client: AsyncClient):
    """Test creating a transaction without auth."""
    response = await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": "00000000-0000-0000-0000-000000000000",
            "transaction_type": "buy",
            "quantity": "1",
            "price": "100",
        },
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_transaction_validation(client: AsyncClient, regular_user: User):
    """Test transaction validation (negative quantity)."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    _, asset_id = await _setup_asset(client, token)

    response = await client.post(
        "/api/v1/transactions/",
        json={
            "asset_id": asset_id,
            "transaction_type": "buy",
            "quantity": "-1",
            "price": "100",
        },
        headers=headers,
    )
    assert response.status_code == 422
