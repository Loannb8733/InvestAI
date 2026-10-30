import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.tasks import snapshots as snapshot_tasks
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import ASSETS, FROZEN_NOW, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
BASE = "/api/v1/dashboard"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
EXCHANGES = {symbol: exchange for symbol, _, exchange, _ in ASSETS}
EXTRA_TRANSACTIONS = [
    ("ETH", "staking", "1", "0", "2025-06-01T10:00:00Z"),
    ("ETH", "unstaking", "0.25", "0", "2025-12-01T10:00:00Z"),
    ("ETH", "staking_reward", "0.05", "0", "2026-01-01T10:00:00Z"),
    ("USDC", "staking", "500", "0", "2026-02-01T10:00:00Z"),
    ("USDC", "staking_reward", "10", "0", "2026-03-01T10:00:00Z"),
    ("AAPL", "dividend", "1", "20", "2026-09-20T10:00:00Z"),
    ("SOL", "buy", "1", "140", "2026-10-15T10:00:00Z"),
]
GLOBAL_ROUTES = [
    ("default", ""),
    ("all_time", "?days=0"),
    ("week", "?days=7"),
    ("quarter", "?days=90"),
    ("year", "?days=365"),
    ("days_negative", "?days=-1"),
    ("days_too_large", "?days=3651"),
    ("munitions_default", "/munitions"),
    ("munitions_aggressive", "/munitions?monthly_dca=1000&profile=aggressive"),
    ("munitions_conservative", "/munitions?monthly_dca=0&profile=conservative"),
    ("munitions_unknown_profile", "/munitions?profile=yolo"),
    ("munitions_negative_dca", "/munitions?monthly_dca=-1"),
    ("historical_default", "/historical-data"),
    ("historical_all_time", "/historical-data?days=0"),
    ("historical_week", "/historical-data?days=7"),
    ("historical_year", "/historical-data?days=365"),
    ("benchmarks_default", "/benchmarks"),
    ("benchmarks_all_time", "/benchmarks?days=0"),
    ("benchmarks_month", "/benchmarks?days=30"),
]
PORTFOLIO_ROUTES = [
    ("portfolio", ""),
    ("portfolio_history", "/history"),
    ("sparklines_default", "/sparklines"),
    ("sparklines_week", "/sparklines?days=7"),
    ("sparklines_too_short", "/sparklines?days=6"),
    ("sparklines_too_long", "/sparklines?days=91"),
]
EMPTY_ROUTES = [
    ("empty", ""),
    ("empty_all_time", "?days=0"),
    ("empty_munitions", "/munitions"),
    ("empty_historical", "/historical-data"),
    ("empty_historical_all_time", "/historical-data?days=0"),
    ("empty_benchmarks", "/benchmarks"),
]
OFFLINE_ROUTES = [
    ("offline", ""),
    ("offline_all_time", "?days=0"),
    ("offline_munitions", "/munitions"),
    ("offline_historical", "/historical-data"),
]


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return UUID_RE.sub("<id>", value)
    return value


class _Recorder:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.mismatches: list[str] = []

    def compare(self, name: str, actual: Any) -> None:
        path = GOLDEN_DIR / f"{name}.json"
        rendered = json.dumps(_plain(actual), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)

    async def shot(self, name: str, url: str, headers: dict[str, str]) -> Any:
        response = await self.client.get(url, headers=headers)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        self.compare(name, {"status": response.status_code, "body": payload})
        return payload


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _portfolio_and_assets(client: AsyncClient, headers: dict[str, str]) -> tuple[str, dict[str, str]]:
    portfolios = (await client.get("/api/v1/portfolios", headers=headers)).json()
    portfolio_id = portfolios[0]["id"]
    assets = (await client.get("/api/v1/assets", headers=headers)).json()
    return portfolio_id, {a["symbol"]: a["id"] for a in assets}


async def _post(client: AsyncClient, url: str, headers: dict[str, str], body: dict[str, Any]) -> None:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == 201, response.text


async def _enrich(client: AsyncClient, headers: dict[str, str], assets: dict[str, str]) -> None:
    for symbol, kind, quantity, price, executed_at in EXTRA_TRANSACTIONS:
        body = {
            "asset_id": assets[symbol],
            "transaction_type": kind,
            "quantity": quantity,
            "price": price,
            "fee": "0",
            "currency": "EUR",
            "executed_at": executed_at,
            "exchange": EXCHANGES[symbol],
        }
        await _post(client, "/api/v1/transactions", headers, body)
    alerts = [
        {"name": "BTC haut", "condition": "price_above", "threshold": 80000, "asset_id": assets["BTC"]},
        {"name": "ETH bas", "condition": "price_below", "threshold": 1000, "asset_id": assets["ETH"]},
    ]
    for alert in alerts:
        await _post(client, "/api/v1/alerts", headers, alert)
    events = [
        {"title": "Dividende AAPL", "event_type": "dividend", "event_date": "2026-11-01T09:00:00Z", "amount": 20},
        {"title": "Échéance lointaine", "event_type": "other", "event_date": "2027-06-01T09:00:00Z"},
        {"title": "Loyer passé", "event_type": "rent", "event_date": "2026-10-01T09:00:00Z", "amount": 500},
    ]
    for event in events:
        await _post(client, "/api/v1/calendar", headers, event)


async def _play(rec: _Recorder, routes: list[tuple[str, str]], prefix: str, headers: dict[str, str]) -> None:
    for name, suffix in routes:
        await rec.shot(name, f"{prefix}{suffix}", headers)


async def _foreign_portfolio_flow(rec: _Recorder, portfolio_id: str, other: dict[str, str]) -> None:
    for name, suffix in (("", ""), ("_history", "/history"), ("_sparklines", "/sparklines")):
        await rec.shot(f"other_user_portfolio{name}", f"{BASE}/portfolio/{portfolio_id}{suffix}", other)
        await rec.shot(f"unknown_portfolio{name}", f"{BASE}/portfolio/{UNKNOWN_ID}{suffix}", other)
        await rec.shot(f"malformed_portfolio{name}", f"{BASE}/portfolio/not-a-uuid{suffix}", other)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
async def test_dashboard_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = _auth(regular_user)
    other = _auth(admin_user)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await _play(rec, EMPTY_ROUTES, BASE, other)
        await seed_portfolio(client, headers)
        portfolio_id, assets = await _portfolio_and_assets(client, headers)
        await _enrich(client, headers, assets)
        await _play(rec, GLOBAL_ROUTES, BASE, headers)
        await _play(rec, PORTFOLIO_ROUTES, f"{BASE}/portfolio/{portfolio_id}", headers)
        await _foreign_portfolio_flow(rec, portfolio_id, other)
        await rec.shot("unauthenticated", BASE, {})
    assert not rec.mismatches, f"golden dashboard différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "deterministic_forecaster")
async def test_dashboard_without_live_quotes_matches_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = _auth(regular_user)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await _play(rec, OFFLINE_ROUTES, BASE, headers)
    assert not rec.mismatches, f"golden dashboard différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
async def test_daily_snapshot_is_written_once(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = _auth(regular_user)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await client.get(f"{BASE}?days=30", headers=headers)
        await client.get(f"{BASE}?days=7", headers=headers)
    rows = (await db_session.execute(select(PortfolioSnapshot))).scalars().all()
    rec.compare(
        "daily_snapshots",
        [
            {
                "portfolio_id": row.portfolio_id,
                "snapshot_date": row.snapshot_date,
                "total_value": row.total_value,
                "total_invested": row.total_invested,
                "total_gain_loss": row.total_gain_loss,
                "currency": row.currency,
            }
            for row in rows
        ],
    )
    assert not rec.mismatches, f"golden dashboard différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


def _snapshot_rows(rows: list[PortfolioSnapshot]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (row.snapshot_date, row.portfolio_id is not None))
    return [
        {
            "scope": "portfolio" if row.portfolio_id else "global",
            "snapshot_date": row.snapshot_date,
            "total_value": row.total_value,
            "total_invested": row.total_invested,
            "total_gain_loss": row.total_gain_loss,
            "currency": row.currency,
        }
        for row in ordered
    ]


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
async def test_snapshot_tasks_match_golden(
    client: AsyncClient,
    db_session: AsyncSession,
    regular_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_tasks, "session_factory", TestSessionLocal)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, _auth(regular_user))
        first = await snapshot_tasks._create_all_snapshots_async()
        second = await snapshot_tasks._create_all_snapshots_async()
        rows = (await db_session.execute(select(PortfolioSnapshot))).scalars().all()
        rec.compare("task_snapshots", {"first": first, "second": second, "rows": _snapshot_rows(list(rows))})
        kept = await snapshot_tasks._cleanup_old_snapshots_async(365)
    with time_machine.travel(FROZEN_NOW + timedelta(days=366), tick=False):
        purged = await snapshot_tasks._cleanup_old_snapshots_async(365)
    rec.compare("task_cleanup", {"kept": kept, "purged": purged})
    assert not rec.mismatches, f"golden dashboard différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
