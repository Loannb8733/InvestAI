import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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
BASE = "/api/v1/strategies"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
USER_STRATEGY = {
    "name": "Renfort BTC",
    "description": "Achat mensuel",
    "params": {"frequency": "monthly"},
    "actions": [
        {"action": "BUY", "symbol": "BTC", "amount": 100, "reason": "DCA"},
        {"action": "SELL", "symbol": "ETH", "amount": 0.5, "currency": "EUR"},
    ],
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
    def __init__(self, client: AsyncClient, ids: dict[str, str]) -> None:
        self.client = client
        self.ids = ids
        self.mismatches: list[str] = []

    async def shot(self, name: str, method: str, url: str, headers: dict[str, str], body: Any = None) -> Any:
        response = await self.client.request(method, url, headers=headers, json=body)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        _compare(name, _plain({"status": response.status_code, "body": payload}, self.ids), self.mismatches)
        return payload


async def _user_strategy_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str]) -> None:
    await rec.shot("list_empty", "GET", BASE, headers)
    created = await rec.shot("create", "POST", BASE, headers, USER_STRATEGY)
    sid = created["id"]
    buy, sell = created["actions"][0]["id"], created["actions"][1]["id"]
    await rec.shot("create_minimal", "POST", BASE, headers, {"name": "Vide"})
    await rec.shot("create_empty_name", "POST", BASE, headers, {"name": ""})
    await rec.shot("create_bad_action", "POST", BASE, headers, {"name": "X", "actions": [{"action": ""}]})
    await rec.shot(
        "update_name_status", "PATCH", f"{BASE}/{sid}", headers, {"name": "Renfort BTC v2", "status": "PAUSED"}
    )
    await rec.shot("update_params_only", "PATCH", f"{BASE}/{sid}", headers, {"params": {"frequency": "weekly"}})
    await rec.shot("update_unknown_status", "PATCH", f"{BASE}/{sid}", headers, {"status": "ARCHIVED"})
    await rec.shot("update_unknown", "PATCH", f"{BASE}/{UNKNOWN_ID}", headers, {"name": "X"})
    await rec.shot("update_other_user", "PATCH", f"{BASE}/{sid}", other, {"name": "X"})
    await rec.shot("update_malformed_id", "PATCH", f"{BASE}/not-a-uuid", headers, {"name": "X"})
    await rec.shot("action_execute", "PATCH", f"{BASE}/actions/{buy}", headers, {"status": "EXECUTED", "amount": 150})
    await rec.shot("action_skip", "PATCH", f"{BASE}/actions/{sell}", headers, {"status": "SKIPPED"})
    await rec.shot("action_amount_only", "PATCH", f"{BASE}/actions/{sell}", headers, {"amount": 0.75})
    await rec.shot("action_unknown_status", "PATCH", f"{BASE}/actions/{sell}", headers, {"status": "DONE"})
    await rec.shot("action_unknown", "PATCH", f"{BASE}/actions/{UNKNOWN_ID}", headers, {"status": "SKIPPED"})
    await rec.shot("action_other_user", "PATCH", f"{BASE}/actions/{buy}", other, {"status": "SKIPPED"})
    await rec.shot("performance", "GET", f"{BASE}/{sid}/performance", headers)
    await rec.shot("performance_unknown", "GET", f"{BASE}/{UNKNOWN_ID}/performance", headers)
    await rec.shot("list_two", "GET", BASE, headers)
    await rec.shot("delete_other_user", "DELETE", f"{BASE}/{sid}", other)
    await rec.shot("delete", "DELETE", f"{BASE}/{sid}", headers)
    await rec.shot("delete_again", "DELETE", f"{BASE}/{sid}", headers)


async def _ai_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str]) -> None:
    await rec.shot("ai_suggest", "POST", f"{BASE}/ai-suggest", headers)
    suggested = await rec.shot("ai_suggest_again", "POST", f"{BASE}/ai-suggest", headers)
    await rec.shot("ai_suggest_empty_user", "POST", f"{BASE}/ai-suggest", other)
    if suggested:
        first, last = suggested[0]["id"], suggested[-1]["id"]
        await rec.shot("accept", "PATCH", f"{BASE}/{first}/accept", headers)
        await rec.shot("reject", "PATCH", f"{BASE}/{last}/reject", headers)
        await rec.shot("accept_other_user", "PATCH", f"{BASE}/{first}/accept", other)
        await rec.shot("delete_ai", "DELETE", f"{BASE}/{first}", headers)
    await rec.shot("reject_unknown", "PATCH", f"{BASE}/{UNKNOWN_ID}/reject", headers)
    await rec.shot("list_after_ai", "GET", BASE, headers)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
async def test_strategies_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = _Recorder(client, {})
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await _user_strategy_flow(rec, headers, other)
        await _ai_flow(rec, headers, other)
        await rec.shot("unauthenticated", "GET", BASE, {})
    assert not rec.mismatches, f"golden strategies différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
