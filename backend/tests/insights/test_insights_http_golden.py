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
from app.domains.market_data.history import reader
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import ASSETS, FROZEN_NOW, seed_history, seed_portfolio

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
INSIGHTS = "/api/v1/insights"
SMART = "/api/v1/smart-insights"
EXCHANGES = {symbol: exchange for symbol, _, exchange, _ in ASSETS}
EXTRA_TRANSACTIONS = [
    {"symbol": "ETH", "transaction_type": "staking_reward", "quantity": "0.05", "price": "2500", "day": "2026-01-01"},
    {"symbol": "ETH", "transaction_type": "staking_reward", "quantity": "0.01", "price": "0", "day": "2026-04-01"},
    {"symbol": "UNI", "transaction_type": "airdrop", "quantity": "5", "price": "8", "day": "2026-05-10"},
    {"symbol": "AAPL", "transaction_type": "dividend", "quantity": "1", "price": "20", "day": "2026-09-20"},
    {"symbol": "DOGE", "transaction_type": "interest", "quantity": "100", "price": "0.15", "day": "2026-09-25"},
    {
        "symbol": "SOL",
        "transaction_type": "buy",
        "quantity": "1",
        "price": "140",
        "fee": "2",
        "fee_currency": "USD",
        "currency": "USD",
        "day": "2026-06-15",
    },
    {
        "symbol": "BTC",
        "transaction_type": "buy",
        "quantity": "0.01",
        "price": "55000",
        "fee": "0.0001",
        "fee_currency": "BTC",
        "day": "2026-07-01",
    },
    {
        "symbol": "ARB",
        "transaction_type": "buy",
        "quantity": "100",
        "price": "1",
        "fee": "0.5",
        "fee_currency": "BNB",
        "day": "2026-08-01",
    },
    {"symbol": "UNI", "transaction_type": "fee", "quantity": "1", "price": "9", "day": "2026-08-15"},
]
ROUTES = [
    ("fees", f"{INSIGHTS}/fees"),
    ("tax_loss", f"{INSIGHTS}/tax-loss-harvesting"),
    ("passive_income", f"{INSIGHTS}/passive-income"),
    ("passive_income_2026", f"{INSIGHTS}/passive-income?year=2026"),
    ("passive_income_2020", f"{INSIGHTS}/passive-income?year=2020"),
    ("passive_income_bad_year", f"{INSIGHTS}/passive-income?year=abc"),
    ("backtest_recent", f"{INSIGHTS}/backtest-dca?symbol=BTC&start_year=2026&start_month=1"),
    ("backtest_before_history", f"{INSIGHTS}/backtest-dca?symbol=BTC&monthly_amount=250"),
    ("backtest_unknown_symbol", f"{INSIGHTS}/backtest-dca?symbol=XYZ&start_year=2026"),
    ("backtest_future", f"{INSIGHTS}/backtest-dca?symbol=BTC&start_year=2027"),
    ("backtest_lowercase", f"{INSIGHTS}/backtest-dca?symbol=btc"),
    ("backtest_no_symbol", f"{INSIGHTS}/backtest-dca"),
    ("backtest_low_amount", f"{INSIGHTS}/backtest-dca?symbol=BTC&monthly_amount=0"),
    ("backtest_bad_month", f"{INSIGHTS}/backtest-dca?symbol=BTC&start_month=13"),
    ("backtest_old_year", f"{INSIGHTS}/backtest-dca?symbol=BTC&start_year=2009"),
    ("backtest_asset_type", f"{INSIGHTS}/backtest-dca?symbol=AAPL&asset_type=nimporte&start_year=2026"),
    ("health_default", f"{SMART}/health"),
    ("health_week", f"{SMART}/health?days=7"),
    ("health_year", f"{SMART}/health?days=365"),
    ("health_too_short", f"{SMART}/health?days=6"),
    ("health_too_long", f"{SMART}/health?days=366"),
    ("summary_default", f"{SMART}/summary"),
    ("summary_year", f"{SMART}/summary?days=365"),
    ("anomalies", f"{SMART}/anomalies-impact"),
]
EMPTY_ROUTES = [
    ("empty_fees", f"{INSIGHTS}/fees"),
    ("empty_tax_loss", f"{INSIGHTS}/tax-loss-harvesting"),
    ("empty_passive_income", f"{INSIGHTS}/passive-income"),
    ("empty_health", f"{SMART}/health"),
    ("empty_summary", f"{SMART}/summary"),
    ("empty_anomalies", f"{SMART}/anomalies-impact"),
]
OFFLINE_ROUTES = [
    ("offline_fees", f"{INSIGHTS}/fees"),
    ("offline_tax_loss", f"{INSIGHTS}/tax-loss-harvesting"),
    ("offline_health", f"{SMART}/health"),
    ("offline_summary", f"{SMART}/summary"),
]
UNAUTHENTICATED_ROUTES = [
    ("unauthenticated_fees", f"{INSIGHTS}/fees"),
    ("unauthenticated_health", f"{SMART}/health"),
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

    async def play(self, routes: list[tuple[str, str]], headers: dict[str, str]) -> None:
        for name, url in routes:
            response = await self.client.get(url, headers=headers)
            try:
                body = response.json()
            except ValueError:
                body = response.text
            self._compare(name, {"status": response.status_code, "body": body})

    def _compare(self, name: str, actual: Any) -> None:
        path = GOLDEN_DIR / f"{name}.json"
        rendered = json.dumps(_plain(actual), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _enrich(client: AsyncClient, headers: dict[str, str]) -> None:
    assets = (await client.get("/api/v1/assets", headers=headers)).json()
    ids = {asset["symbol"]: asset["id"] for asset in assets}
    for entry in EXTRA_TRANSACTIONS:
        fields = dict(entry)
        symbol = fields.pop("symbol")
        body = {
            "asset_id": ids[symbol],
            "fee": "0",
            "currency": "EUR",
            "executed_at": f"{fields.pop('day')}T10:00:00Z",
            "exchange": EXCHANGES[symbol],
            **fields,
        }
        response = await client.post("/api/v1/transactions", json=body, headers=headers)
        assert response.status_code == 201, response.text


@pytest.fixture
def isolated_insights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "session_factory", TestSessionLocal)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster", "isolated_insights")
async def test_insights_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = _auth(regular_user)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await rec.play(EMPTY_ROUTES, _auth(admin_user))
        await seed_portfolio(client, headers)
        await _enrich(client, headers)
        await rec.play(ROUTES, headers)
        await rec.play(UNAUTHENTICATED_ROUTES, {})
    assert not rec.mismatches, f"golden insights différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "deterministic_forecaster", "isolated_insights")
async def test_insights_without_live_quotes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = _auth(regular_user)
    rec = _Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        await _enrich(client, headers)
        await rec.play(OFFLINE_ROUTES, headers)
    assert not rec.mismatches, f"golden insights différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
