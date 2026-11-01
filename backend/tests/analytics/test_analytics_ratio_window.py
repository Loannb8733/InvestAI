from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.history import reader
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

BASE = "/api/v1/analytics"
RATIOS = ("sharpe_ratio", "sortino_ratio", "calmar_ratio")


async def _analytics(client: AsyncClient, url: str, headers: dict[str, str]) -> Any:
    response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _asset_ratios(body: Any) -> dict[str, tuple[float, float]]:
    return {asset["symbol"]: (asset["sharpe_ratio"], asset["sortino_ratio"]) for asset in body["assets"]}


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
class TestRatiosOverAtLeastThreeMonths:
    @pytest.fixture
    async def headers(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> dict[str, str]:
        monkeypatch.setattr(reader, "session_factory", TestSessionLocal)
        auth = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, auth)
        return auth

    async def test_a_short_period_reports_the_three_month_ratios(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            week = await _analytics(client, f"{BASE}?days=7", headers)
            quarter = await _analytics(client, f"{BASE}?days=90", headers)
        assert {name: week[name] for name in RATIOS} == {name: quarter[name] for name in RATIOS}
        assert _asset_ratios(week) == _asset_ratios(quarter)

    async def test_a_short_period_keeps_its_own_volatility(self, client: AsyncClient, headers: dict[str, str]) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            week = await _analytics(client, f"{BASE}?days=7", headers)
            quarter = await _analytics(client, f"{BASE}?days=90", headers)
        assert week["portfolio_volatility"] != quarter["portfolio_volatility"]

    async def test_a_portfolio_follows_the_same_rule(self, client: AsyncClient, headers: dict[str, str]) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            portfolio_id = (await client.get("/api/v1/portfolios", headers=headers)).json()[0]["id"]
            week = await _analytics(client, f"{BASE}/portfolio/{portfolio_id}?days=7", headers)
            quarter = await _analytics(client, f"{BASE}/portfolio/{portfolio_id}?days=90", headers)
        assert {name: week[name] for name in RATIOS} == {name: quarter[name] for name in RATIOS}

    async def test_a_long_period_keeps_its_own_ratios(self, client: AsyncClient, headers: dict[str, str]) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            year = await _analytics(client, f"{BASE}?days=365", headers)
            quarter = await _analytics(client, f"{BASE}?days=90", headers)
        assert year["sharpe_ratio"] != quarter["sharpe_ratio"]

    async def test_the_all_period_covers_the_whole_history(self, client: AsyncClient, headers: dict[str, str]) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            summary = (await _analytics(client, f"{BASE}/performance?period=all", headers))["summary"]
            history = await _analytics(client, f"{BASE}?days=0", headers)
        assert summary["sharpe_ratio"] == history["sharpe_ratio"]
        assert summary["volatility"] == history["portfolio_volatility"]
