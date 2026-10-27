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

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.sample_portfolio import FROZEN_NOW

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at"})
BASE = "/api/v1/calendar"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
PROJECT = {
    "platform": "Anaxago",
    "project_name": "Résidence des Tilleuls",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 24,
    "start_date": "2025-10-01",
    "estimated_end_date": "2027-10-01",
    "interest_frequency": "quarterly",
}
SHORT_PROJECT = {**PROJECT, "project_name": "Lofts", "duration_months": 12, "start_date": "2026-06-01"}


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
        plain = _plain({"status": response.status_code, "body": payload}, self.ids)
        rendered = json.dumps(plain, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        path = GOLDEN_DIR / f"{name}.json"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)
        return payload


def _event(title: str, event_type: str, when: str, **extra: Any) -> dict[str, Any]:
    return {"title": title, "event_type": event_type, "event_date": when, **extra}


async def _empty_flow(rec: _Recorder, headers: dict[str, str]) -> None:
    await rec.shot("event_types", "GET", f"{BASE}/event-types", headers)
    await rec.shot("summary_empty", "GET", f"{BASE}/summary", headers)
    await rec.shot("events_empty", "GET", BASE, headers)
    await rec.shot("upcoming_empty", "GET", f"{BASE}/upcoming", headers)
    await rec.shot("passive_income_empty", "GET", f"{BASE}/passive-income", headers)


async def _create_flow(rec: _Recorder, headers: dict[str, str]) -> dict[str, str]:
    plans = {
        "dividend": _event("Dividende AAPL", "dividend", "2026-11-15T09:00:00Z", amount=12.5, description="T4"),
        "rent": _event(
            "Loyer T2", "rent", "2026-10-05T09:00:00Z", amount=800, is_recurring=True, recurrence_rule="FREQ=MONTHLY"
        ),
        "usd": _event("Coupon US", "interest", "2026-12-01T09:00:00Z", amount=100, currency="USD"),
        "weekly": _event(
            "Point hebdo", "reminder", "2026-10-10T09:00:00Z", is_recurring=True, recurrence_rule="WEEKLY"
        ),
        "leap": _event(
            "Bonus bissextile",
            "dividend",
            "2028-02-29T09:00:00Z",
            amount=5,
            is_recurring=True,
            recurrence_rule="YEARLY",
        ),
        "zero": _event("Échéance nulle", "payment_due", "2026-10-20T09:00:00Z", amount=0),
        "past": _event("Intérêts septembre", "interest", "2026-09-01T09:00:00Z", amount=50),
        "naive": _event("Sans fuseau", "other", "2026-10-25T10:00:00"),
    }
    ids = {}
    for key, body in plans.items():
        ids[key] = (await rec.shot(f"create_{key}", "POST", BASE, headers, body))["id"]
    refusals = {
        "create_empty_title": _event("", "other", "2026-10-25T10:00:00Z"),
        "create_long_title": _event("X" * 201, "other", "2026-10-25T10:00:00Z"),
        "create_bad_type": _event("X", "birthday", "2026-10-25T10:00:00Z"),
        "create_bad_date": _event("X", "other", "demain"),
    }
    for name, body in refusals.items():
        await rec.shot(name, "POST", BASE, headers, body)
    return ids


async def _read_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str], ids: dict[str, str]) -> None:
    await rec.shot("events_all", "GET", BASE, headers)
    await rec.shot("events_rent", "GET", f"{BASE}?event_type=rent", headers)
    await rec.shot("events_income", "GET", f"{BASE}?income_only=true", headers)
    window = "start_date=2026-10-01T00:00:00Z&end_date=2026-10-31T23:59:59Z"
    await rec.shot("events_october", "GET", f"{BASE}?{window}", headers)
    await rec.shot("events_paged", "GET", f"{BASE}?skip=2&limit=3", headers)
    await rec.shot("upcoming", "GET", f"{BASE}/upcoming", headers)
    await rec.shot("upcoming_90", "GET", f"{BASE}/upcoming?days=90", headers)
    await rec.shot("summary", "GET", f"{BASE}/summary", headers)
    await rec.shot("passive_income", "GET", f"{BASE}/passive-income", headers)
    await rec.shot("event_get", "GET", f"{BASE}/{ids['dividend']}", headers)
    await rec.shot("event_get_unknown", "GET", f"{BASE}/{UNKNOWN_ID}", headers)
    await rec.shot("event_get_other_user", "GET", f"{BASE}/{ids['dividend']}", other)
    await rec.shot("event_get_malformed", "GET", f"{BASE}/not-a-uuid", headers)


async def _tax_flow(rec: _Recorder, headers: dict[str, str]) -> None:
    await rec.shot("seed_tax", "POST", f"{BASE}/seed-tax-events", headers)
    await rec.shot("seed_tax_again", "POST", f"{BASE}/seed-tax-events", headers)
    await rec.shot("events_tax", "GET", f"{BASE}?event_type=tax_deadline", headers)


async def _mutation_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str], ids: dict[str, str]) -> None:
    url = f"{BASE}/{ids['dividend']}"
    await rec.shot("patch", "PATCH", url, headers, {"title": "Dividende Apple", "amount": 13, "currency": "USD"})
    await rec.shot("patch_complete", "PATCH", url, headers, {"is_completed": True})
    await rec.shot("patch_reopen", "PATCH", url, headers, {"is_completed": False})
    await rec.shot("patch_clear_description", "PATCH", url, headers, {"description": None})
    await rec.shot("patch_other_user", "PATCH", url, other, {"title": "X"})
    rent = f"{BASE}/{ids['rent']}/complete"
    await rec.shot("complete_recurring", "POST", rent, headers)
    await rec.shot("complete_recurring_again", "POST", rent, headers)
    await rec.shot("events_rent_after_complete", "GET", f"{BASE}?event_type=rent", headers)
    await rec.shot("complete_leap_year", "POST", f"{BASE}/{ids['leap']}/complete", headers)
    await rec.shot("complete_unknown", "POST", f"{BASE}/{UNKNOWN_ID}/complete", headers)
    await rec.shot("complete_other_user", "POST", f"{BASE}/{ids['past']}/complete", other)
    await rec.shot("summary_after_mutations", "GET", f"{BASE}/summary", headers)
    await rec.shot("delete_other_user", "DELETE", url, other)
    await rec.shot("delete", "DELETE", url, headers)
    await rec.shot("delete_again", "DELETE", url, headers)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
async def test_calendar_routes_match_golden(client: AsyncClient, regular_user: User, admin_user: User) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _empty_flow(rec, headers)
        await client.post("/api/v1/crowdfunding", headers=headers, json=PROJECT)
        await client.post(
            "/api/v1/crowdfunding", headers=headers, json={**SHORT_PROJECT, "estimated_end_date": "2027-06-01"}
        )
        ids = await _create_flow(rec, headers)
        await _read_flow(rec, headers, other, ids)
        await _tax_flow(rec, headers)
        await _mutation_flow(rec, headers, other, ids)
        await rec.shot("unauthenticated", "GET", BASE, {})
    assert not rec.mismatches, f"golden calendar différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
