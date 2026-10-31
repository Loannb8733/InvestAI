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

from app.core.config import settings
from app.core.db import session as db_session_module
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.system import router
from app.domains.system.scheduler import Scheduler, beat_entries
from tests.conftest import TestSessionLocal, test_engine
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at", "last_duration_s"})
CRON = "/api/v1/cron"
SECRET = "jeton-de-caracterisation"
CRON_ROUTES = ("sync-goals", "invariants-check")
JOBS = ("sync-exchanges", "create-daily-snapshots", "refresh-contrarian-stats", "check-regime-mutation")
SESSION_FACTORY_USERS = (
    "app.core.db.session",
    "app.domains.exchanges.sync.runner",
    "app.domains.dashboard.snapshots.tasks",
    "app.services.regime_alert_service",
)


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


@pytest.fixture
def cron_on_test_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", SECRET)
    monkeypatch.setattr(db_session_module, "engine", test_engine)
    for module in SESSION_FACTORY_USERS:
        monkeypatch.setattr(f"{module}.session_factory", TestSessionLocal)
    monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)
    monkeypatch.setattr(router, "api_scheduler", Scheduler({entry.name: entry for entry in beat_entries()}))


async def _guard_flow(rec: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as disabled:
        disabled.setattr(settings, "CRON_SECRET", "")
        await rec.shot("cron_disabled", "POST", f"{CRON}/sync-goals", {"X-Cron-Token": SECRET})
    await rec.shot("cron_without_token", "POST", f"{CRON}/sync-goals", {})
    await rec.shot("cron_wrong_token", "POST", f"{CRON}/sync-goals", {"X-Cron-Token": "faux"})
    await rec.shot("cron_get", "GET", f"{CRON}/sync-goals", {"X-Cron-Token": SECRET})


async def _seed(client: AsyncClient, db: AsyncSession, headers: dict[str, str]) -> None:
    await seed_history(db)
    await seed_portfolio(client, headers)
    goal = {"name": "Apport", "target_amount": "150000", "deadline_date": "2029-06-30", "strategy_type": "moderate"}
    await client.post("/api/v1/goals", headers=headers, json=goal)


async def _cron_flow(rec: _Recorder) -> None:
    token = {"X-Cron-Token": SECRET}
    for route in CRON_ROUTES:
        await rec.shot(f"cron_{route}", "POST", f"{CRON}/{route}", token)
    for job in JOBS:
        await rec.shot(f"job_{job}", "POST", f"{CRON}/jobs/{job}", token)
    await rec.shot("job_create-daily-snapshots_again", "POST", f"{CRON}/jobs/create-daily-snapshots", token)
    await rec.shot("job_check-regime-mutation_again", "POST", f"{CRON}/jobs/check-regime-mutation", token)
    await rec.shot("job_unknown", "POST", f"{CRON}/jobs/inconnue", token)


async def _status_flow(rec: _Recorder, admin: dict[str, str], regular: dict[str, str]) -> None:
    await rec.shot("status_admin", "GET", "/api/v1/system/status", admin)
    await rec.shot("status_regular_user", "GET", "/api/v1/system/status", regular)
    await rec.shot("status_unauthenticated", "GET", "/api/v1/system/status", {})


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "cron_on_test_db")
async def test_system_routes_match_golden(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regular = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    admin = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _guard_flow(rec, monkeypatch)
        await _seed(client, db_session, regular)
        await _cron_flow(rec)
        await _status_flow(rec, admin, regular)
    assert not rec.mismatches, f"golden system différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
