import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_cached_dashboard
from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.dashboard.snapshots import tasks as snapshot_tasks
from app.domains.dashboard.snapshots.periods import format_date_for_period
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

BASE = "/api/v1/dashboard"
EXPECTED_GAIN = 26565.0
EXPECTED_REALIZED = 5487.0
EXPECTED_UNREALIZED = 21078.0
EXPECTED_INVESTED = 47500.0
MIGRATION = Path(__file__).parents[2] / "alembic" / "versions" / "b7e2c4d9f1a6_dividend_quantity.py"


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _assets(client: AsyncClient, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    response = await client.get("/api/v1/assets", headers=headers)
    return {asset["symbol"]: asset for asset in response.json()}


async def _dividend(client: AsyncClient, headers: dict[str, str], asset_id: str, exchange: str | None) -> None:
    body = {
        "asset_id": asset_id,
        "transaction_type": "dividend",
        "quantity": "1",
        "price": "20",
        "fee": "0",
        "currency": "EUR",
        "executed_at": "2026-09-20T10:00:00Z",
        "exchange": exchange,
    }
    response = await client.post("/api/v1/transactions", json=body, headers=headers)
    assert response.status_code == 201, response.text


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
class TestWithLiveQuotes:
    async def test_total_gain_counts_sales_and_leaves_stablecoins_out(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            body = (await client.get(BASE, headers=headers)).json()
        assert body["total_gain_loss"] == pytest.approx(EXPECTED_GAIN)
        assert body["net_gain_loss"] == pytest.approx(EXPECTED_GAIN)
        assert body["total_gain_loss_percent"] == pytest.approx(EXPECTED_GAIN / EXPECTED_INVESTED * 100)

    async def test_breakdown_is_realized_plus_unrealized_with_fees_counted_once(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            body = (await client.get(BASE, headers=headers)).json()
        breakdown = body["advanced_metrics"]["pnl_breakdown"]
        assert breakdown["realized_pnl"] == pytest.approx(EXPECTED_REALIZED)
        assert breakdown["unrealized_pnl"] == pytest.approx(EXPECTED_UNREALIZED)
        assert breakdown["total_pnl"] == pytest.approx(EXPECTED_GAIN)
        assert breakdown["net_pnl"] == pytest.approx(EXPECTED_GAIN)

    async def test_all_time_change_is_the_total_gain(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            body = (await client.get(f"{BASE}?days=0", headers=headers)).json()
        assert body["period_change"] == pytest.approx(EXPECTED_GAIN)

    async def test_portfolio_route_reports_the_same_gain(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            portfolio_id = (await client.get("/api/v1/portfolios", headers=headers)).json()[0]["id"]
            body = (await client.get(f"{BASE}/portfolio/{portfolio_id}", headers=headers)).json()
        assert body["total_gain_loss"] == pytest.approx(EXPECTED_GAIN)

    async def test_route_and_task_snapshots_record_the_same_gain(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(snapshot_tasks, "session_factory", TestSessionLocal)
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            await snapshot_tasks.create_all_snapshots()
            rows = (await db_session.execute(select(PortfolioSnapshot))).scalars().all()
            assert {float(row.total_gain_loss) for row in rows} == {EXPECTED_GAIN}
            await db_session.execute(text("DELETE FROM portfolio_snapshots"))
            await db_session.commit()
            db_session.expire_all()
            await client.get(BASE, headers=headers)
            rows = (await db_session.execute(select(PortfolioSnapshot))).scalars().all()
        assert [float(row.total_gain_loss) for row in rows] == [EXPECTED_GAIN]

    async def test_benchmark_portfolio_series_uses_iso_dates_and_covers_all_time(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            month = (await client.get(f"{BASE}/benchmarks?days=30", headers=headers)).json()
            all_time = (await client.get(f"{BASE}/benchmarks?days=0", headers=headers)).json()
        points = next(series for series in month if series["symbol"] == "PORTFOLIO")["data"]
        assert all(datetime.strptime(point["date"], "%Y-%m-%d") for point in points)
        assert "PORTFOLIO" in {series["symbol"] for series in all_time}

    async def test_dividend_keeps_the_quantity_and_counts_without_a_platform(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            apple = (await _assets(client, headers))["AAPL"]
            await _dividend(client, headers, apple["id"], None)
            assert float((await _assets(client, headers))["AAPL"]["quantity"]) == 20
            portfolio_id = (await client.get("/api/v1/portfolios", headers=headers)).json()[0]["id"]
            body = (await client.get(f"{BASE}/portfolio/{portfolio_id}", headers=headers)).json()
        position = next(entry for entry in body["assets"] if entry["symbol"] == "AAPL")
        assert position["dividend_income"] == pytest.approx(20)
        assert body["total_dividend_income"] == pytest.approx(20)

    async def test_migration_removes_quantity_added_by_past_dividends(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_portfolio(client, headers)
            apple = (await _assets(client, headers))["AAPL"]
            await _dividend(client, headers, apple["id"], "Trade Republic")
        await db_session.execute(text("UPDATE assets SET quantity = 21 WHERE symbol = 'AAPL'"))
        await db_session.execute(text(_migration().REMOVE_DIVIDEND_QUANTITY))
        await db_session.commit()
        db_session.expire_all()
        stored = (await db_session.execute(select(Asset).where(Asset.symbol == "AAPL"))).scalar_one()
        assert float(stored.quantity) == 20

    async def test_screen_and_metrics_do_not_share_a_cache_entry(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            await client.get(BASE, headers=headers)
        user_id = str(regular_user.id)
        screen = await get_cached_dashboard(user_id, 30, "EUR")
        metrics = await get_cached_dashboard(user_id, 30, "EUR", section="metrics")
        assert screen is not None
        assert "advanced_metrics" in screen
        assert metrics is not None
        assert "aggregated_assets" in metrics

    async def test_upcoming_events_do_not_depend_on_the_period(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        event = {"title": "Dividende", "event_type": "dividend", "event_date": "2026-11-01T09:00:00Z", "amount": 20}
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            response = await client.post("/api/v1/calendar", json=event, headers=headers)
            assert response.status_code == 201, response.text
            body = (await client.get(f"{BASE}?days=7", headers=headers)).json()
        assert [entry["title"] for entry in body["upcoming_events"]] == ["Dividende"]

    async def test_no_symbol_is_flagged_when_every_quote_is_live(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            body = (await client.get(BASE, headers=headers)).json()
        assert body["unpriced_symbols"] == []


@pytest.mark.usefixtures("empty_test_redis", "offline", "deterministic_forecaster")
async def test_positions_without_a_quote_are_flagged(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = _auth(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        body = (await client.get(BASE, headers=headers)).json()
    assert body["unpriced_symbols"] == ["AAPL", "ARB", "BTC", "DOGE", "ETH", "SOL", "UNI"]


@pytest.mark.usefixtures("empty_test_redis", "offline", "deterministic_forecaster")
class TestRequestsAndEmptyAccount:
    @pytest.mark.parametrize("suffix", ["", "/history", "/sparklines"])
    async def test_malformed_portfolio_id_is_rejected(
        self, client: AsyncClient, regular_user: User, suffix: str
    ) -> None:
        response = await client.get(f"{BASE}/portfolio/not-a-uuid{suffix}", headers=_auth(regular_user))
        assert response.status_code == 422

    async def test_unknown_munitions_profile_is_rejected(self, client: AsyncClient, regular_user: User) -> None:
        response = await client.get(f"{BASE}/munitions?profile=yolo", headers=_auth(regular_user))
        assert response.status_code == 422

    async def test_empty_account_is_not_shown_as_fully_invested(self, client: AsyncClient, regular_user: User) -> None:
        response = await client.get(f"{BASE}/munitions", headers=_auth(regular_user))
        assert response.json()["invested_pct"] == 0

    async def test_empty_account_has_no_period_on_all_time(self, client: AsyncClient, regular_user: User) -> None:
        response = await client.get(f"{BASE}?days=0", headers=_auth(regular_user))
        assert response.json()["period_days"] == 0


@pytest.mark.parametrize(
    ("moment", "label"),
    [(datetime(2026, 9, 17, tzinfo=UTC), "17 sept."), (datetime(2026, 2, 3, tzinfo=UTC), "03 févr.")],
)
def test_series_months_are_in_french(moment: datetime, label: str) -> None:
    assert format_date_for_period(moment, 30) == label


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dividend_quantity", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
