import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at"})
GOALS = "/api/v1/goals"
SIMS = "/api/v1/simulations"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
FIRE = {"annual_expenses": 30000, "seed": 7}
ASSET_GOAL = {
    "name": "Apport immobilier",
    "goal_type": "asset",
    "target_amount": "150000",
    "deadline_date": "2029-06-30",
    "priority": "high",
    "strategy_type": "aggressive",
    "notes": "Résidence principale",
}
SAVINGS_GOAL = {
    "name": "Matelas de sécurité",
    "goal_type": "savings",
    "target_amount": "10000",
    "target_date": "2027-12-31",
}


def _plain(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: "<volatile>" if k in VOLATILE_KEYS else _plain(v, ids) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_plain(v, ids) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return UUID_RE.sub(lambda m: ids.setdefault(m.group(0), f"<id-{len(ids)}>"), value)
    return value


def _compare(name: str, actual: Any, mismatches: list[str]) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    rendered = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    elif path.read_text(encoding="utf-8") != rendered:
        mismatches.append(name)


class _Recorder:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.ids: dict[str, str] = {}
        self.mismatches: list[str] = []

    async def shot(self, name: str, method: str, url: str, headers: dict[str, str], body: Any = None) -> Any:
        response = await self.client.request(method, url, headers=headers, json=body)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        _compare(name, _plain({"status": response.status_code, "body": payload}, self.ids), self.mismatches)
        return payload


@pytest.fixture
def seeded_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    real = np.random.default_rng

    def default_rng(seed: Any = None) -> np.random.Generator:
        return real(20261017 if seed is None else seed)

    monkeypatch.setattr(np.random, "default_rng", default_rng)


async def _goals_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str]) -> None:
    await rec.shot("goals_empty", "GET", GOALS, headers)
    asset = await rec.shot("goal_create_asset", "POST", GOALS, headers, ASSET_GOAL)
    savings = await rec.shot("goal_create_savings", "POST", GOALS, headers, SAVINGS_GOAL)
    gid, sid = asset["id"], savings["id"]
    await rec.shot("goal_create_cash_name", "POST", GOALS, headers, {"name": "usdt", "target_amount": "100"})
    await rec.shot(
        "goal_create_bad_date",
        "POST",
        GOALS,
        headers,
        {"name": "X", "target_amount": "1", "deadline_date": "2029-13-01"},
    )
    await rec.shot("goal_create_zero_target", "POST", GOALS, headers, {"name": "X", "target_amount": "0"})
    await rec.shot(
        "goal_create_bad_priority", "POST", GOALS, headers, {"name": "X", "target_amount": "1", "priority": "urgent"}
    )
    await rec.shot("goals_two", "GET", GOALS, headers)
    await rec.shot("goals_paged", "GET", f"{GOALS}?skip=1&limit=1", headers)
    await rec.shot("goal_get", "GET", f"{GOALS}/{gid}", headers)
    await rec.shot("goal_get_unknown", "GET", f"{GOALS}/{UNKNOWN_ID}", headers)
    await rec.shot("goal_get_other_user", "GET", f"{GOALS}/{gid}", other)
    await rec.shot("goal_get_malformed", "GET", f"{GOALS}/not-a-uuid", headers)
    await rec.shot("goal_projection", "GET", f"{GOALS}/{gid}/projection", headers)
    await rec.shot("goal_projection_dca", "GET", f"{GOALS}/{gid}/projection?monthly_contribution=500", headers)
    await rec.shot("goal_projection_savings", "GET", f"{GOALS}/{sid}/projection", headers)
    await rec.shot("goal_projection_unknown", "GET", f"{GOALS}/{UNKNOWN_ID}/projection", headers)
    await rec.shot("goal_patch_name_status", "PATCH", f"{GOALS}/{gid}", headers, {"name": "Apport", "status": "paused"})
    await rec.shot("goal_patch_bad_date", "PATCH", f"{GOALS}/{gid}", headers, {"deadline_date": "demain"})
    await rec.shot("goal_patch_reached", "PATCH", f"{GOALS}/{sid}", headers, {"current_amount": "12000"})
    await rec.shot("goal_patch_other_user", "PATCH", f"{GOALS}/{gid}", other, {"name": "X"})
    await rec.shot("goal_sync", "POST", f"{GOALS}/{gid}/sync", headers)
    await rec.shot("goal_sync_unknown", "POST", f"{GOALS}/{UNKNOWN_ID}/sync", headers)
    await rec.shot("goal_delete_other_user", "DELETE", f"{GOALS}/{gid}", other)
    await rec.shot("goal_delete", "DELETE", f"{GOALS}/{gid}", headers)
    await rec.shot("goal_delete_again", "DELETE", f"{GOALS}/{gid}", headers)
    await rec.shot("goals_after_delete", "GET", GOALS, headers)


async def _simulations_flow(rec: _Recorder, headers: dict[str, str], empty: dict[str, str]) -> None:
    await rec.shot("fire_defaults", "POST", f"{SIMS}/fire-probabilistic", headers, FIRE)
    explicit = {
        **FIRE,
        "current_value": 100000,
        "monthly_contribution": 1500,
        "annual_return_mean": 0.06,
        "annual_volatility": 0.15,
        "index_contributions": True,
        "years_horizon": 20,
        "n_paths": 500,
    }
    await rec.shot("fire_explicit", "POST", f"{SIMS}/fire-probabilistic", headers, explicit)
    await rec.shot(
        "fire_unseeded", "POST", f"{SIMS}/fire-probabilistic", headers, {"annual_expenses": 30000, "n_paths": 200}
    )
    await rec.shot("fire_bad_rate", "POST", f"{SIMS}/fire-probabilistic", headers, {**FIRE, "withdrawal_rate": 0.1})
    await rec.shot("fire_empty_user", "POST", f"{SIMS}/fire-probabilistic", empty, FIRE)
    await rec.shot("projection_defaults", "POST", f"{SIMS}/projection", headers, {})
    body = {"years": 25, "expected_return": 5, "expense_ratio": 0.3, "monthly_contribution": 400, "inflation_rate": 3}
    await rec.shot("projection_explicit", "POST", f"{SIMS}/projection", headers, body)
    await rec.shot(
        "projection_nominal", "POST", f"{SIMS}/projection", headers, {"years": 5, "inflation_adjustment": False}
    )
    await rec.shot("projection_bad_years", "POST", f"{SIMS}/projection", headers, {"years": 0})
    await rec.shot("projection_empty_user", "POST", f"{SIMS}/projection", empty, {})
    await rec.shot("dca_monthly", "POST", f"{SIMS}/dca", headers, {"total_amount": 12000})
    await rec.shot(
        "dca_weekly",
        "POST",
        f"{SIMS}/dca",
        headers,
        {"total_amount": 5200, "frequency": "weekly", "duration_months": 6},
    )
    await rec.shot(
        "dca_quarterly",
        "POST",
        f"{SIMS}/dca",
        headers,
        {"total_amount": 8000, "frequency": "quarterly", "duration_months": 24, "expected_volatility": 60},
    )
    await rec.shot(
        "dca_unknown_frequency", "POST", f"{SIMS}/dca", headers, {"total_amount": 1000, "frequency": "daily"}
    )
    await rec.shot("dca_bad_amount", "POST", f"{SIMS}/dca", headers, {"total_amount": 0})


async def _saved_simulations_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str]) -> None:
    await rec.shot("sims_empty", "GET", SIMS, headers)
    body = {"name": "FIRE 2040", "simulation_type": "fire", "parameters": {"annual_expenses": 30000}}
    created = await rec.shot("sim_create", "POST", SIMS, headers, body)
    sim_id = created["id"]
    await rec.shot("sim_create_dca", "POST", SIMS, headers, {"name": "DCA", "simulation_type": "dca", "parameters": {}})
    await rec.shot(
        "sim_create_bad_type", "POST", SIMS, headers, {"name": "X", "simulation_type": "lottery", "parameters": {}}
    )
    await rec.shot("sims_two", "GET", SIMS, headers)
    await rec.shot("sims_filtered", "GET", f"{SIMS}?simulation_type=dca", headers)
    await rec.shot("sim_get", "GET", f"{SIMS}/{sim_id}", headers)
    await rec.shot("sim_get_unknown", "GET", f"{SIMS}/{UNKNOWN_ID}", headers)
    await rec.shot("sim_get_other_user", "GET", f"{SIMS}/{sim_id}", other)
    await rec.shot("sim_delete_other_user", "DELETE", f"{SIMS}/{sim_id}", other)
    await rec.shot("sim_delete", "DELETE", f"{SIMS}/{sim_id}", headers)
    await rec.shot("sim_delete_again", "DELETE", f"{SIMS}/{sim_id}", headers)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "seeded_rng")
async def test_planning_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await _goals_flow(rec, headers, other)
        await _simulations_flow(rec, headers, other)
        await _saved_simulations_flow(rec, headers, other)
        await rec.shot("unauthenticated", "GET", GOALS, {})
    assert not rec.mismatches, f"golden planning différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
