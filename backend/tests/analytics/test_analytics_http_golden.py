import json
import math
import os
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.history.models import AssetPriceHistory

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VOLATILE_KEYS = frozenset({"created_at", "updated_at", "last_updated", "computed_at", "generated_at"})
FROZEN_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
HISTORY_DAYS = 420

ASSETS = [
    ("BTC", "crypto", "Binance", "60000"),
    ("ETH", "crypto", "Kraken", "3000"),
    ("SOL", "crypto", "Tangem", "150"),
    ("AAPL", "stock", "Trade Republic", "200"),
]
TRANSACTIONS = [
    ("BTC", "buy", "0.5", "30000", "10", "2025-01-10T10:00:00Z"),
    ("BTC", "buy", "0.25", "50000", "5", "2025-08-01T10:00:00Z"),
    ("ETH", "buy", "4", "2000", "4", "2025-02-15T10:00:00Z"),
    ("ETH", "sell", "1", "3500", "3", "2026-03-01T10:00:00Z"),
    ("SOL", "buy", "50", "100", "2", "2025-04-01T10:00:00Z"),
    ("AAPL", "buy", "20", "170", "1", "2025-05-20T10:00:00Z"),
]
SERIES = {
    "BTC": (40000, 0.0012, 0.08, 23, 0.0),
    "ETH": (2200, 0.0009, 0.11, 17, 1.0),
    "SOL": (90, 0.0015, 0.15, 13, 2.0),
    "AAPL": (165, 0.0004, 0.04, 31, 0.5),
    "PAXG": (2000, 0.0003, 0.02, 41, 1.5),
    "SPY": (480, 0.0003, 0.03, 29, 0.7),
    "IWDA.AS": (85, 0.00025, 0.025, 37, 0.9),
    "^GSPC": (5000, 0.0003, 0.03, 29, 0.6),
    "^IXIC": (16000, 0.0004, 0.045, 27, 1.2),
}

GET_ROUTES = [
    ("global_default", "/api/v1/analytics"),
    ("global_all_history", "/api/v1/analytics?days=0"),
    ("global_year", "/api/v1/analytics?days=365"),
    ("portfolio_default", "/api/v1/analytics/portfolio/{portfolio_id}"),
    ("portfolio_unknown", "/api/v1/analytics/portfolio/00000000-0000-0000-0000-000000000000"),
    ("correlation_default", "/api/v1/analytics/correlation"),
    ("correlation_30d_portfolio", "/api/v1/analytics/correlation?days=30&portfolio_id={portfolio_id}"),
    ("diversification_default", "/api/v1/analytics/diversification"),
    ("diversification_portfolio", "/api/v1/analytics/diversification?portfolio_id={portfolio_id}"),
    ("performance_1d", "/api/v1/analytics/performance?period=1d"),
    ("performance_7d", "/api/v1/analytics/performance?period=7d"),
    ("performance_30d", "/api/v1/analytics/performance"),
    ("performance_90d", "/api/v1/analytics/performance?period=90d"),
    ("performance_1y", "/api/v1/analytics/performance?period=1y"),
    ("performance_all", "/api/v1/analytics/performance?period=all"),
    ("performance_portfolio", "/api/v1/analytics/performance?period=90d&portfolio_id={portfolio_id}"),
    ("stress_test_default", "/api/v1/analytics/stress-test"),
    ("stress_test_portfolio", "/api/v1/analytics/stress-test?portfolio_id={portfolio_id}"),
    ("beta_default", "/api/v1/analytics/beta"),
    ("beta_30d", "/api/v1/analytics/beta?days=30"),
    ("monte_carlo_default", "/api/v1/analytics/monte-carlo"),
    ("monte_carlo_short", "/api/v1/analytics/monte-carlo?horizon=30&simulations=1000"),
    (
        "monte_carlo_withdrawals",
        "/api/v1/analytics/monte-carlo?horizon=365&simulations=1000&annual_withdrawal_rate=4&ter_percentage=0.2",
    ),
    ("monte_carlo_monthly", "/api/v1/analytics/monte-carlo?horizon=180&simulations=1000&monthly_withdrawal=500"),
    ("xirr", "/api/v1/analytics/xirr"),
    ("optimize_max_sharpe", "/api/v1/analytics/optimize"),
    ("optimize_min_volatility", "/api/v1/analytics/optimize?objective=min_volatility&days=180"),
    ("platform_distribution", "/api/v1/analytics/distribution/platforms"),
]
EMPTY_ROUTES = [
    ("empty_global", "/api/v1/analytics"),
    ("empty_correlation", "/api/v1/analytics/correlation"),
    ("empty_diversification", "/api/v1/analytics/diversification"),
    ("empty_performance", "/api/v1/analytics/performance"),
    ("empty_stress_test", "/api/v1/analytics/stress-test"),
    ("empty_beta", "/api/v1/analytics/beta"),
    ("empty_monte_carlo", "/api/v1/analytics/monte-carlo?simulations=1000"),
    ("empty_xirr", "/api/v1/analytics/xirr"),
    ("empty_optimize", "/api/v1/analytics/optimize"),
    ("empty_platform_distribution", "/api/v1/analytics/distribution/platforms"),
]


def _normalize(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: "<volatile>" if k in VOLATILE_KEYS else _normalize(v, ids) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize(v, ids) for v in value]
    if isinstance(value, str) and UUID_RE.match(value):
        return ids.setdefault(value, f"<id-{len(ids)}>")
    if isinstance(value, float):
        return round(value, 4)
    return value


def _price(symbol: str, day: int) -> Decimal:
    base, drift, amplitude, period, phase = SERIES[symbol]
    value = base * (1 + drift * day) * (1 + amplitude * math.sin(day / period + phase))
    return Decimal(str(round(value, 6)))


async def _seed_history(db: AsyncSession) -> None:
    start = FROZEN_NOW.date() - timedelta(days=HISTORY_DAYS)
    for symbol in SERIES:
        for day in range(HISTORY_DAYS + 1):
            moment: date = start + timedelta(days=day)
            db.add(AssetPriceHistory(symbol=symbol, price_date=moment, price_eur=_price(symbol, day), source="test"))
    await db.commit()


async def _seed_portfolio(client: AsyncClient, headers: dict[str, str]) -> str:
    portfolio = await client.post("/api/v1/portfolios", json={"name": "Analytics"}, headers=headers)
    assert portfolio.status_code == 201, portfolio.text
    portfolio_id: str = portfolio.json()["id"]
    asset_ids: dict[str, str] = {}
    for symbol, kind, exchange, price in ASSETS:
        body = {
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "asset_type": kind,
            "exchange": exchange,
            "current_price": price,
        }
        asset = await client.post("/api/v1/assets", json=body, headers=headers)
        assert asset.status_code == 201, asset.text
        asset_ids[symbol] = asset.json()["id"]
    for symbol, kind, quantity, price, fee, executed_at in TRANSACTIONS:
        exchange = next(e for s, _, e, _ in ASSETS if s == symbol)
        body = {
            "asset_id": asset_ids[symbol],
            "transaction_type": kind,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "currency": "EUR",
            "executed_at": executed_at,
            "exchange": exchange,
        }
        tx = await client.post("/api/v1/transactions", json=body, headers=headers)
        assert tx.status_code == 201, tx.text
    return portfolio_id


def _compare(name: str, actual: dict[str, Any], mismatches: list[str]) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    rendered = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    elif path.read_text(encoding="utf-8") != rendered:
        mismatches.append(name)


async def _snapshot(client: AsyncClient, method: str, url: str, headers: dict[str, str], **kwargs: Any) -> Any:
    response = await client.request(method, url, headers=headers, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


@pytest.mark.usefixtures("empty_test_redis", "offline")
async def test_analytics_routes_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    empty = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    mismatches: list[str] = []
    ids: dict[str, str] = {}
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed_history(db_session)
        portfolio_id = await _seed_portfolio(client, headers)
        scenarios: list[tuple[str, str, str, dict[str, str], dict[str, Any]]] = [
            (name, "GET", url.format(portfolio_id=portfolio_id), headers, {}) for name, url in GET_ROUTES
        ]
        scenarios += [
            ("portfolio_of_someone_else", "GET", f"/api/v1/analytics/portfolio/{portfolio_id}", empty, {}),
            (
                "rebalance_equal",
                "POST",
                "/api/v1/analytics/rebalance",
                headers,
                {"json": {"BTC": 25, "ETH": 25, "SOL": 25, "AAPL": 25}},
            ),
            ("rebalance_new_symbol", "POST", "/api/v1/analytics/rebalance", headers, {"json": {"BTC": 50, "DOT": 50}}),
            ("rebalance_bad_total", "POST", "/api/v1/analytics/rebalance", headers, {"json": {"BTC": 60, "ETH": 20}}),
        ]
        scenarios += [(name, "GET", url, empty, {}) for name, url in EMPTY_ROUTES]
        for name, method, url, who, kwargs in scenarios:
            status, body = await _snapshot(client, method, url, who, **kwargs)
            _compare(name, {"status": status, "body": _normalize(body, ids)}, mismatches)
    assert not mismatches, f"golden analytics différent : {mismatches} (GOLDEN_UPDATE=1 pour accepter)"
