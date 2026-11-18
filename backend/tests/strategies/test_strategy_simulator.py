"""Le simulateur ne dépend que des paramètres saisis : ni positions, ni liquidité, ni signaux, ni scores alpha."""

import json
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.service import metrics_service
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.predictions.service import prediction_service
from app.domains.strategies.service import strategy_service
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
BASE = "/api/v1/strategies"
DCA = {
    "template": "dca",
    "assets": [{"symbol": "BTC", "weight_pct": 70}, {"symbol": "ETH", "weight_pct": 30}],
    "amount_per_period": 50,
    "frequency": "monthly",
    "periods": 3,
    "start_date": "2026-11-01",
}
VCA = {
    "template": "vca",
    "symbol": "SOL",
    "target_increment": 40,
    "frequency": "weekly",
    "periods": 3,
    "start_date": "2026-10-01",
}
PROFIT_TAKING = {
    "template": "profit_taking",
    "symbol": "BTC",
    "quantity": 0.2,
    "tiers": [{"price": 60000, "sell_pct": 25}, {"price": 90000, "sell_pct": 50}],
}
REBALANCE = {
    "template": "rebalance",
    "lines": [
        {"symbol": "BTC", "target_pct": 60, "current_value": 900},
        {"symbol": "ETH", "target_pct": 40, "current_value": 300},
    ],
    "threshold_pct": 5,
    "frequency": "quarterly",
    "periods": 2,
    "start_date": "2026-11-01",
}
RECOMMENDATION_WORDS = ("achat fort", "conviction", "alpha", "liquidit", "munitions", "signal")


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


@pytest.fixture
def forbidden_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Toute lecture des signaux, du tableau de bord ou de la capacité de déploiement échoue et est notée."""
    calls: list[str] = []

    def _trap(name: str) -> Any:
        async def _read(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"le simulateur ne doit pas appeler {name}")

        return _read

    monkeypatch.setattr(prediction_service, "get_strategy_map", _trap("get_strategy_map"))
    monkeypatch.setattr(metrics_service, "get_user_dashboard_metrics", _trap("get_user_dashboard_metrics"))
    monkeypatch.setattr(strategy_service, "get_deployment_capacity", _trap("get_deployment_capacity"))
    return calls


async def _seed(client: AsyncClient, db: AsyncSession, user: User) -> dict[str, str]:
    headers = _headers(user)
    await seed_history(db)
    await seed_portfolio(client, headers)
    return headers


@pytest.mark.parametrize("params", [DCA, VCA, PROFIT_TAKING, REBALANCE], ids=lambda p: p["template"])
async def test_the_same_parameters_give_the_same_simulation_whatever_the_portfolio(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    admin_user: User,
    forbidden_reads: list[str],
    params: dict[str, Any],
) -> None:
    body = {"params": params, "backtest_start": "2026-01-15"}
    with time_machine.travel(FROZEN_NOW, tick=False):
        invested_user = await _seed(client, db_session, regular_user)
        forbidden_reads.clear()
        with_portfolio = await client.post(f"{BASE}/simulate", json=body, headers=invested_user)
        without_portfolio = await client.post(f"{BASE}/simulate", json=body, headers=_headers(admin_user))
    assert with_portfolio.status_code == 200, with_portfolio.text
    assert with_portfolio.json() == without_portfolio.json()
    assert with_portfolio.json()["backtest"]["available"]
    assert forbidden_reads == []


async def test_saved_amounts_are_exactly_those_of_the_parameters(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, forbidden_reads: list[str]
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seed(client, db_session, regular_user)
        forbidden_reads.clear()
        response = await client.post(f"{BASE}/from-template", json={"name": "DCA", "params": DCA}, headers=headers)
    created = response.json()
    assert response.status_code == 201, response.text
    assert (created["source"], created["status"]) == ("USER", "ACTIVE")
    assert (created["ai_reasoning"], created["market_regime"], created["confidence"]) == (None, None, None)
    assert created["params"]["template"] == "dca"
    assert created["rule_summary"].startswith("Achat périodique : 50,00 € chaque mois, 3 échéances")
    assert [(a["action"], a["symbol"], a["amount"], a["status"]) for a in created["actions"]] == [
        ("BUY", "BTC", 35.0, "PENDING"),
        ("BUY", "ETH", 15.0, "PENDING"),
    ] * 3
    assert [a["scheduled_at"][:10] for a in created["actions"][::2]] == ["2026-11-01", "2026-12-01", "2027-01-01"]
    assert forbidden_reads == []


@pytest.mark.parametrize("params", [DCA, VCA, PROFIT_TAKING, REBALANCE], ids=lambda p: p["template"])
async def test_nothing_reads_as_a_recommendation(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, params: dict[str, Any]
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seed(client, db_session, regular_user)
        simulated = await client.post(
            f"{BASE}/simulate", json={"params": params, "backtest_start": "2026-01-15"}, headers=headers
        )
        created = await client.post(f"{BASE}/from-template", json={"name": "X", "params": params}, headers=headers)
    text = json.dumps([simulated.json(), created.json()], ensure_ascii=False).lower()
    assert not [word for word in RECOMMENDATION_WORDS if word in text]
    assert "pas un conseil en investissement" in simulated.json()["disclaimer"]


async def test_an_invalid_rule_creates_nothing(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    bad = {**DCA, "assets": [{"symbol": "BTC", "weight_pct": 50}]}
    response = await client.post(f"{BASE}/from-template", json={"name": "X", "params": bad}, headers=headers)
    assert response.status_code == 422
    assert (await client.get(BASE, headers=headers)).json() == []


async def test_a_vca_amount_entered_at_execution_is_measured(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers = await _seed(client, db_session, regular_user)
        created = (
            await client.post(f"{BASE}/from-template", json={"name": "VCA", "params": VCA}, headers=headers)
        ).json()
        second = created["actions"][1]
        await client.patch(f"{BASE}/actions/{second['id']}", json={"status": "EXECUTED", "amount": 42}, headers=headers)
        performance = (await client.get(f"{BASE}/{created['id']}/performance", headers=headers)).json()
    assert [a["amount"] for a in created["actions"]] == [40.0, None, None]
    assert [(line["symbol"], line["direction"], line["amount_eur"]) for line in performance["lines"]] == [
        ("SOL", "buy", 42.0)
    ]
