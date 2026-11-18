import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio
from tests.strategies.legacy import seed_legacy_ai_strategies

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
BASE = "/api/v1/strategies"


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _seeded(client: AsyncClient, db: AsyncSession, user: User) -> dict[str, str]:
    headers = _headers(user)
    await seed_history(db)
    await seed_portfolio(client, headers)
    return headers


async def test_an_unknown_strategy_status_is_rejected_as_invalid(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    created = (await client.post(BASE, json={"name": "X"}, headers=headers)).json()
    response = await client.patch(f"{BASE}/{created['id']}", json={"status": "ARCHIVED"}, headers=headers)
    assert response.status_code == 422


async def test_an_unknown_action_status_is_rejected_as_invalid(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    body = {"name": "X", "actions": [{"action": "BUY", "symbol": "BTC", "amount": 10}]}
    action_id = (await client.post(BASE, json=body, headers=headers)).json()["actions"][0]["id"]
    response = await client.patch(f"{BASE}/actions/{action_id}", json={"status": "DONE"}, headers=headers)
    assert response.status_code == 422


async def test_the_suggestion_route_is_gone_and_legacy_proposals_remain(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        proposed, _ = await seed_legacy_ai_strategies(db_session, regular_user)
        suggested = await client.post(f"{BASE}/ai-suggest", headers=headers)
        listed = (await client.get(BASE, headers=headers)).json()
    assert suggested.status_code == 405
    assert [s["status"] for s in listed if s["id"] == str(proposed.id)] == ["PROPOSED"]
    assert len(listed) == 2


async def test_legacy_ai_strategies_still_display_and_measure(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        _, accepted = await seed_legacy_ai_strategies(db_session, regular_user)
        listed = (await client.get(BASE, headers=headers)).json()
        performance = (await client.get(f"{BASE}/{accepted.id}/performance", headers=headers)).json()
    assert all(s["rule_summary"] is None and s["source"] == "AI" for s in listed)
    assert {line["action"]: line["direction"] for line in performance["lines"]} == {
        "ACHAT FORT": "buy",
        "ALLÉGER": "sell",
    }
    assert performance["non_evaluable_count"] == 0
