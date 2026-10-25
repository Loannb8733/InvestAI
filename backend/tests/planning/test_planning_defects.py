from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.classification import is_cash_like
from tests.sample_portfolio import FROZEN_NOW, fake_quote, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
GOALS = "/api/v1/goals"


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _seeded(client: AsyncClient, db: AsyncSession, user: User) -> dict[str, str]:
    headers = _headers(user)
    await seed_history(db)
    await seed_portfolio(client, headers)
    return headers


async def test_projection_texts_name_months_in_french(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        body = {
            "name": "Apport",
            "target_amount": "150000",
            "deadline_date": "2029-06-30",
            "strategy_type": "aggressive",
        }
        goal = (await client.post(GOALS, json=body, headers=headers)).json()
        projection = (await client.get(f"{GOALS}/{goal['id']}/projection", headers=headers)).json()
    assert "cible en juin 2029" in projection["alert_message"]
    assert projection["eta_date"] == "sept. 2029"
    assert projection["curve"][0]["date_label"] == "oct. 2026"


async def test_an_unknown_dca_frequency_is_rejected(client: AsyncClient, regular_user: User) -> None:
    body = {"total_amount": 1000, "frequency": "daily"}
    response = await client.post("/api/v1/simulations/dca", json=body, headers=_headers(regular_user))
    assert response.status_code == 422


async def test_syncing_a_savings_goal_only_prices_liquid_assets(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    priced: list[str] = []

    async def recording_quote(symbol: str, asset_type: Any, currency: str = "EUR") -> Any:
        priced.append(symbol)
        return await fake_quote(symbol, asset_type, currency)

    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        monkeypatch.setattr(price_feed, "quote", recording_quote)
        body = {"name": "Matelas", "goal_type": "savings", "target_amount": "10000"}
        goal = (await client.post(GOALS, json=body, headers=headers)).json()
        synced = (await client.post(f"{GOALS}/{goal['id']}/sync", headers=headers)).json()
    assert priced and all(is_cash_like(symbol) for symbol in priced)
    assert synced["current_amount"] == goal["current_amount"]
