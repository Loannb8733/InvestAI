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
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from tests.sample_portfolio import FROZEN_NOW, fake_quote, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at"})
BASE = "/api/v1/alerts"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
DAILY_MOVES = {"BTC": 3.5, "DOGE": -6.0}


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
        rendered = (
            json.dumps(
                _plain({"status": response.status_code, "body": payload}, self.ids),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        path = GOLDEN_DIR / f"{name}.json"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)
        return payload


@pytest.fixture
def moving_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def quote(symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote | None:
        base = await fake_quote(symbol, asset_type, currency)
        if base is None:
            return None
        return PriceQuote(price=base.price, change_percent_24h=DAILY_MOVES.get(symbol.upper(), 0.0))

    monkeypatch.setattr(price_feed, "quote", quote)


async def _asset_ids(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    assets = (await client.get("/api/v1/assets", headers=headers)).json()
    return {asset["symbol"]: asset["id"] for asset in assets}


def _alert(name: str, condition: str, threshold: float, asset_id: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"name": name, "condition": condition, "threshold": threshold, "asset_id": asset_id, **extra}


async def _create_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str], assets: dict[str, str]) -> str:
    await rec.shot("conditions", "GET", f"{BASE}/conditions", headers)
    await rec.shot("summary_empty", "GET", f"{BASE}/summary", headers)
    await rec.shot("alerts_empty", "GET", BASE, headers)
    created = await rec.shot(
        "create_price_above", "POST", BASE, headers, _alert("BTC haut", "price_above", 50000, assets["BTC"])
    )
    plans = [
        ("create_price_below", _alert("ETH bas", "price_below", 2000, assets["ETH"], notify_email=False)),
        ("create_change_up", _alert("SOL +10", "change_percent_up", 10, assets["SOL"])),
        ("create_change_down", _alert("ARB -20", "change_percent_down", 20, assets["ARB"])),
        ("create_daily_up", _alert("BTC jour", "daily_change_up", 3, assets["BTC"])),
        ("create_daily_down", _alert("DOGE jour", "daily_change_down", 5, assets["DOGE"])),
        ("create_break_even", _alert("ETH rentable", "target_break_even", 0, assets["ETH"])),
        ("create_volatility", _alert("BTC risque", "volatility_spike", 0, assets["BTC"], currency="USD")),
        ("create_drawdown", _alert("Repli", "portfolio_drawdown", 5)),
        ("create_hhi", _alert("Concentration", "concentration_hhi", 0.3)),
        ("create_drift", _alert("Dérive", "allocation_drift", 10)),
        ("create_zero_threshold", _alert("X", "price_above", 0, assets["BTC"])),
        ("create_portfolio_with_asset", _alert("X", "portfolio_drawdown", 5, assets["BTC"])),
        ("create_missing_asset", _alert("X", "price_above", 1)),
        ("create_unknown_asset", _alert("X", "price_above", 1, UNKNOWN_ID)),
        ("create_bad_condition", _alert("X", "price_sideways", 1, assets["BTC"])),
        ("create_long_name", _alert("X" * 101, "price_above", 1, assets["BTC"])),
    ]
    for name, body in plans:
        await rec.shot(name, "POST", BASE, headers, body)
    await rec.shot("create_other_users_asset", "POST", BASE, other, _alert("X", "price_above", 1, assets["BTC"]))
    alert_id: str = created["id"]
    return alert_id


async def _read_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str], alert_id: str) -> None:
    await rec.shot("alerts_all", "GET", BASE, headers)
    await rec.shot("alerts_paged", "GET", f"{BASE}?skip=2&limit=3", headers)
    await rec.shot("alert_get", "GET", f"{BASE}/{alert_id}", headers)
    await rec.shot("alert_get_unknown", "GET", f"{BASE}/{UNKNOWN_ID}", headers)
    await rec.shot("alert_get_other_user", "GET", f"{BASE}/{alert_id}", other)
    await rec.shot("alert_get_malformed", "GET", f"{BASE}/not-a-uuid", headers)
    await rec.shot("summary", "GET", f"{BASE}/summary", headers)


async def _check_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str]) -> None:
    await rec.shot("check", "POST", f"{BASE}/check", headers)
    await rec.shot("check_again", "POST", f"{BASE}/check", headers)
    await rec.shot("check_other_user", "POST", f"{BASE}/check", other)
    await rec.shot("notifications_after_check", "GET", "/api/v1/notifications", headers)
    await rec.shot("alerts_after_check", "GET", BASE, headers)
    await rec.shot("summary_after_check", "GET", f"{BASE}/summary", headers)


async def _mutation_flow(rec: _Recorder, headers: dict[str, str], other: dict[str, str], alert_id: str) -> None:
    url = f"{BASE}/{alert_id}"
    await rec.shot(
        "patch", "PATCH", url, headers, {"name": "BTC très haut", "threshold": 70000, "notify_in_app": False}
    )
    await rec.shot("patch_deactivate", "PATCH", url, headers, {"is_active": False})
    await rec.shot("alerts_active_only", "GET", f"{BASE}?active_only=true", headers)
    await rec.shot("patch_zero_threshold", "PATCH", url, headers, {"threshold": 0})
    await rec.shot("patch_other_user", "PATCH", url, other, {"name": "X"})
    await rec.shot("patch_unknown", "PATCH", f"{BASE}/{UNKNOWN_ID}", headers, {"name": "X"})
    await rec.shot("delete_other_user", "DELETE", url, other)
    await rec.shot("delete", "DELETE", url, headers)
    await rec.shot("delete_again", "DELETE", url, headers)
    await rec.shot("alerts_after_delete", "GET", BASE, headers)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "moving_quotes")
async def test_alert_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        alert_id = await _create_flow(rec, headers, other, await _asset_ids(client, headers))
        await _read_flow(rec, headers, other, alert_id)
        await _check_flow(rec, headers, other)
        with time_machine.travel(FROZEN_NOW + timedelta(minutes=6), tick=False):
            await rec.shot("check_after_cooldown", "POST", f"{BASE}/check", headers)
            await rec.shot("summary_after_second_check", "GET", f"{BASE}/summary", headers)
        await _mutation_flow(rec, headers, other, alert_id)
        await rec.shot("unauthenticated", "GET", BASE, {})
    assert not rec.mismatches, f"golden alerts différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
