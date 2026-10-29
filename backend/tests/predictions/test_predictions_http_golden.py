import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.notifications.telegram.client import telegram_service
from app.domains.predictions import alerts as prediction_alerts
from app.domains.predictions.models import PredictionLog
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at", "generated_at", "computed_at", "timestamp", "last_updated"})
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"

GET_ROUTES = [
    ("portfolio_default", "/api/v1/predictions/portfolio"),
    ("portfolio_1d", "/api/v1/predictions/portfolio?days=1"),
    ("portfolio_30d", "/api/v1/predictions/portfolio?days=30"),
    ("portfolio_days_too_low", "/api/v1/predictions/portfolio?days=0"),
    ("portfolio_days_too_high", "/api/v1/predictions/portfolio?days=31"),
    ("anomalies", "/api/v1/predictions/anomalies"),
    ("sentiment", "/api/v1/predictions/sentiment"),
    ("market_cycle", "/api/v1/predictions/market-cycle"),
    ("top_alpha", "/api/v1/predictions/top-alpha"),
    ("validate_signal", "/api/v1/predictions/validate-signal"),
    ("validate_signal_eth_buy", "/api/v1/predictions/validate-signal?symbol=ETH&action=ACHAT"),
    ("validate_signal_unknown_symbol", "/api/v1/predictions/validate-signal?symbol=XRP"),
    ("strategy_map", "/api/v1/predictions/strategy-map"),
    ("events", "/api/v1/predictions/events"),
    ("backtest_default", "/api/v1/predictions/backtest"),
    ("backtest_30d", "/api/v1/predictions/backtest?days=30"),
    ("track_record_btc", "/api/v1/predictions/track-record/btc"),
    ("track_record_btc_limit", "/api/v1/predictions/track-record/BTC?limit=2"),
    ("track_record_unknown", "/api/v1/predictions/track-record/XRP"),
]
WHAT_IF = [
    ("what_if", {"scenarios": [{"symbol": "BTC", "change_percent": -30}, {"symbol": "ETH", "change_percent": 50}]}),
    ("what_if_unknown_symbol", {"scenarios": [{"symbol": "XRP", "change_percent": 10}]}),
    ("what_if_empty", {"scenarios": []}),
    ("what_if_out_of_range", {"scenarios": [{"symbol": "BTC", "change_percent": 600}]}),
]
EMPTY_ROUTES = [
    "/api/v1/predictions/portfolio",
    "/api/v1/predictions/anomalies",
    "/api/v1/predictions/sentiment",
    "/api/v1/predictions/market-cycle",
    "/api/v1/predictions/top-alpha",
    "/api/v1/predictions/validate-signal",
    "/api/v1/predictions/strategy-map",
    "/api/v1/predictions/backtest",
    "/api/v1/predictions/planned-orders",
]
TELEGRAM_ROUTES = [
    "/api/v1/predictions/market-cycle",
    "/api/v1/predictions/top-alpha",
    "/api/v1/predictions/validate-signal",
    "/api/v1/predictions/strategy-map",
]


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


async def _snapshot(
    client: AsyncClient, method: str, url: str, headers: dict[str, str], ids: dict[str, str], **kwargs: Any
) -> Any:
    response = await client.request(method, url, headers=headers, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return _plain({"status": response.status_code, "body": body}, ids)


async def _seed_prediction_logs(db: AsyncSession, user: User) -> None:
    for i, (predicted, actual, low, high) in enumerate(
        [
            (61000.0, 60000.0, 58000.0, 63000.0),
            (59000.0, 60500.0, 57500.0, 60000.0),
            (62000.0, 61800.0, 60000.0, 64000.0),
        ]
    ):
        created = FROZEN_NOW - timedelta(days=30 - 7 * i)
        db.add(
            PredictionLog(
                user_id=user.id,
                symbol="BTC",
                asset_type="crypto",
                model_name="ensemble",
                prediction_data={"horizon": 7},
                predicted_price=predicted,
                price_at_creation=Decimal("60000"),
                target_date=(created + timedelta(days=7)).replace(tzinfo=None),
                horizon_days=7,
                actual_price=actual,
                error_pct=abs(predicted - actual) / actual * 100,
                confidence_low=low,
                confidence_high=high,
                accuracy_checked=(created + timedelta(days=7)).replace(tzinfo=None),
                mape=abs(predicted - actual) / actual * 100,
                direction_correct=(predicted > 60000) == (actual > 60000),
                ci_covered=low <= actual <= high,
                created_at=created,
            )
        )
    await db.commit()


async def _planned_orders(
    client: AsyncClient, headers: dict[str, str], other: dict[str, str], ids: dict[str, str]
) -> list[tuple[str, Any]]:
    base = "/api/v1/predictions/planned-orders"
    shots = [("planned_orders_empty", await _snapshot(client, "GET", base, headers, ids))]
    created = await client.post(base, json={"symbol": "eth", "side": "buy", "amount_eur": 250.456}, headers=headers)
    shots.append(("planned_order_create", _plain({"status": created.status_code, "body": created.json()}, ids)))
    order_id = created.json()["id"]
    bodies = [
        ("planned_order_create_sell", {"symbol": "SOL", "side": "sell", "amount_eur": 100, "notes": "MPT"}),
        ("planned_order_bad_side", {"symbol": "SOL", "side": "hold", "amount_eur": 100}),
        ("planned_order_bad_symbol", {"symbol": "SO L", "side": "buy", "amount_eur": 100}),
        ("planned_order_zero_amount", {"symbol": "SOL", "side": "buy", "amount_eur": 0}),
        ("planned_order_bad_source", {"symbol": "SOL", "side": "buy", "amount_eur": 10, "source": "api"}),
    ]
    for name, body in bodies:
        shots.append((name, await _snapshot(client, "POST", base, headers, ids, json=body)))
    shots.append(("planned_orders_two_pending", await _snapshot(client, "GET", base, headers, ids)))
    patches = [
        ("planned_order_patch_other_user", f"{base}/{order_id}", other, {"status": "executed"}),
        ("planned_order_patch_unknown", f"{base}/{UNKNOWN_ID}", headers, {"status": "executed"}),
        ("planned_order_patch_ignored_status", f"{base}/{order_id}", headers, {"status": "pending"}),
        ("planned_order_patch_executed", f"{base}/{order_id}", headers, {"status": "executed"}),
    ]
    for name, url, who, body in patches:
        shots.append((name, await _snapshot(client, "PATCH", url, who, ids, json=body)))
    shots.append(("planned_orders_after_execution", await _snapshot(client, "GET", base, headers, ids)))
    return shots


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
async def test_predictions_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    empty = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    mismatches: list[str] = []
    ids: dict[str, str] = {}
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await _seed_prediction_logs(db_session, regular_user)
        for name, url in GET_ROUTES:
            _compare(name, await _snapshot(client, "GET", url, headers, ids), mismatches)
        for name, body in WHAT_IF:
            snapshot = await _snapshot(client, "POST", "/api/v1/predictions/what-if", headers, ids, json=body)
            _compare(name, snapshot, mismatches)
        for name, snapshot in await _planned_orders(client, headers, empty, ids):
            _compare(name, snapshot, mismatches)
        for url in EMPTY_ROUTES:
            name = "empty_" + url.rsplit("/", 1)[-1].replace("-", "_")
            _compare(name, await _snapshot(client, "GET", url, empty, ids), mismatches)
        _compare("unauthenticated", await _snapshot(client, "GET", "/api/v1/predictions/events", {}, ids), mismatches)
    assert not mismatches, f"golden predictions différent : {mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
async def test_predictions_telegram_alerts_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_service, "send_smart_alert", sent)
    monkeypatch.setattr(prediction_alerts, "alpha_keyboard", MagicMock(return_value={"keyboard": "alpha"}))
    regular_user.telegram_enabled = True
    regular_user.telegram_chat_id = "4242"
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    mismatches: list[str] = []
    ids: dict[str, str] = {}
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        for url in TELEGRAM_ROUTES:
            sent.reset_mock()
            await client.get(url, headers=headers)
            alerts = [call.kwargs for call in sent.await_args_list]
            _compare("telegram_" + url.rsplit("/", 1)[-1].replace("-", "_"), _plain(alerts, ids), mismatches)
    assert not mismatches, f"golden predictions différent : {mismatches} (GOLDEN_UPDATE=1 pour accepter)"
