import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VOLATILE_KEYS = frozenset({"created_at", "updated_at", "last_updated"})
FROZEN_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

TRANSACTIONS = [
    ("GLDCOIN", "buy", "2.0", "1000", "5", "2024-01-15T10:00:00Z"),
    ("GLDCOIN", "buy", "1.0", "1600", "3", "2024-06-10T10:00:00Z"),
    ("GLDCOIN", "sell", "1.5", "2000", "4", "2025-02-20T10:00:00Z"),
    ("GLDTOKEN", "buy", "100", "12", "1", "2024-03-01T10:00:00Z"),
    ("GLDTOKEN", "sell", "40", "9", "1", "2025-05-05T10:00:00Z"),
]
ASSETS = {"GLDCOIN": "1500", "GLDTOKEN": "10"}

ROUTES = [
    ("portfolios", "/api/v1/portfolios"),
    ("transactions", "/api/v1/transactions"),
    ("dashboard", "/api/v1/dashboard"),
    ("dashboard_portfolio", "/api/v1/dashboard/portfolio/{portfolio_id}"),
    ("tax_2025_summary", "/api/v1/reports/tax/2025/summary"),
    ("analytics_performance", "/api/v1/analytics/performance"),
    ("analytics_xirr", "/api/v1/analytics/xirr"),
]


def _normalize(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: "<volatile>" if k in VOLATILE_KEYS else _normalize(v, ids) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize(v, ids) for v in value]
    if isinstance(value, str) and UUID_RE.match(value):
        return ids.setdefault(value, f"<id-{len(ids)}>")
    if isinstance(value, float):
        return round(value, 6)
    return value


async def _seed(client: AsyncClient, headers: dict[str, str]) -> str:
    portfolio = await client.post("/api/v1/portfolios", json={"name": "Golden"}, headers=headers)
    assert portfolio.status_code == 201, portfolio.text
    portfolio_id: str = portfolio.json()["id"]
    asset_ids: dict[str, str] = {}
    for symbol, price in ASSETS.items():
        asset = await client.post(
            "/api/v1/assets",
            json={
                "portfolio_id": portfolio_id,
                "symbol": symbol,
                "asset_type": "crypto",
                "quantity": "0",
                "avg_buy_price": "0",
                "current_price": price,
            },
            headers=headers,
        )
        assert asset.status_code == 201, asset.text
        asset_ids[symbol] = asset.json()["id"]
    for symbol, kind, quantity, price, fee, executed_at in TRANSACTIONS:
        tx = await client.post(
            "/api/v1/transactions",
            json={
                "asset_id": asset_ids[symbol],
                "transaction_type": kind,
                "quantity": quantity,
                "price": price,
                "fee": fee,
                "currency": "EUR",
                "executed_at": executed_at,
                "exchange": "Golden",
            },
            headers=headers,
        )
        assert tx.status_code == 201, tx.text
    return portfolio_id


@pytest.mark.usefixtures("empty_test_redis", "offline")
async def test_api_responses_match_golden_snapshots(client: AsyncClient, regular_user: User) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        mismatches = await _compare_with_snapshots(client, regular_user)
    assert not mismatches, f"golden mismatch: {mismatches} (GOLDEN_UPDATE=1 to accept)"


async def _compare_with_snapshots(client: AsyncClient, user: User) -> list[str]:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    portfolio_id = await _seed(client, headers)
    ids: dict[str, str] = {}
    mismatches: list[str] = []
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    for name, template in ROUTES:
        response = await client.get(template.format(portfolio_id=portfolio_id), headers=headers)
        actual = {"status": response.status_code, "body": _normalize(response.json(), ids)}
        path = SNAPSHOT_DIR / f"{name}.json"
        rendered = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if UPDATE or not path.exists():
            path.write_text(rendered, encoding="utf-8")
            continue
        if path.read_text(encoding="utf-8") != rendered:
            mismatches.append(name)
    return mismatches
