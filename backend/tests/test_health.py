"""Health check and general endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "InvestAI"


@pytest.mark.asyncio
async def test_nonexistent_endpoint(client: AsyncClient):
    """Test 404 for nonexistent endpoint."""
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404
