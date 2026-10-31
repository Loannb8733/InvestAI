from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.services.smart_insights_service import smart_insights_service
from tests.forecaster_double import DeterministicForecaster
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
@pytest.mark.parametrize("route", ["health", "summary"])
async def test_smart_insights_give_analytics_the_requested_window(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: str,
) -> None:
    analytics = smart_insights_service.analytics_service
    build_asset_data = analytics._build_asset_data
    windows: list[int] = []

    async def spy(assets: Any, days: int) -> Any:
        windows.append(days)
        return await build_asset_data(assets, days=days)

    monkeypatch.setattr(analytics, "_build_asset_data", spy)
    monkeypatch.setattr(smart_insights_service.prediction_service, "forecaster", DeterministicForecaster())
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        response = await client.get(f"/api/v1/smart-insights/{route}?days=30", headers=headers)
    assert response.status_code == 200, response.text
    assert "get_portfolio_metrics failed" not in caplog.text
    assert 30 in windows
