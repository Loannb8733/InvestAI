import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

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


async def test_suggesting_again_replaces_the_pending_proposals(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        first = (await client.post(f"{BASE}/ai-suggest", headers=headers)).json()
        await client.patch(f"{BASE}/{first[0]['id']}/accept", headers=headers)
        second = (await client.post(f"{BASE}/ai-suggest", headers=headers)).json()
        listed = (await client.get(BASE, headers=headers)).json()
    proposed = [s["id"] for s in listed if s["status"] == "PROPOSED"]
    assert sorted(proposed) == sorted(s["id"] for s in second)
    assert any(s["id"] == first[0]["id"] and s["status"] == "ACTIVE" for s in listed)


async def test_strategy_names_count_assets_in_french(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seeded(client, db_session, regular_user)
        names = [s["name"] for s in (await client.post(f"{BASE}/ai-suggest", headers=headers)).json()]
    assert not [n for n in names if "assets" in n]
    assert any(n.endswith("1 actif") for n in names)


async def test_an_empty_portfolio_gets_no_suggestion(client: AsyncClient, regular_user: User) -> None:
    response = await client.post(f"{BASE}/ai-suggest", headers=_headers(regular_user))
    assert response.status_code == 200
    assert response.json() == []
