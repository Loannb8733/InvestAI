from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.quotes import RateResolver
from app.domains.dashboard.snapshots.series import _snapshot_point
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.reports.data import ReportDataMixin
from app.domains.reports.platforms import platform_analysis
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

BASE = "/api/v1/dashboard"
EXPECTED_GAIN = 26565.0
EXPECTED_INVESTED = 47500.0


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _seeded_get(
    client: AsyncClient, db_session: AsyncSession, user: User, url: str, *, history: bool = True
) -> Any:
    headers = _auth(user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        if history:
            await seed_history(db_session)
        await seed_portfolio(client, headers)
        response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")
class TestWithLiveQuotes:
    async def test_no_sharpe_under_three_months(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        body = await _seeded_get(client, db_session, regular_user, f"{BASE}?days=30")
        assert body["advanced_metrics"]["risk_metrics"]["sharpe_ratio"] is None

    async def test_sharpe_exists_from_three_months(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        body = await _seeded_get(client, db_session, regular_user, f"{BASE}?days=90")
        assert isinstance(body["advanced_metrics"]["risk_metrics"]["sharpe_ratio"], float)

    async def test_series_gain_counts_sales(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        body = await _seeded_get(client, db_session, regular_user, f"{BASE}/historical-data?days=30")
        last = body[-1]
        assert last["gain_loss"] == pytest.approx(last["value"] - last["net_capital"], abs=0.01)
        assert last["gain_loss"] != pytest.approx(last["value"] - last["invested"], abs=0.01)

    async def test_user_analytics_reports_the_account_gain(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        body = await _seeded_get(client, db_session, regular_user, "/api/v1/analytics")
        assert body["total_gain_loss"] == pytest.approx(EXPECTED_GAIN)
        assert body["total_gain_loss_percent"] == pytest.approx(EXPECTED_GAIN / EXPECTED_INVESTED * 100)

    async def test_portfolio_analytics_reports_the_portfolio_gain(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        headers = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, headers)
            portfolio_id = (await client.get("/api/v1/portfolios", headers=headers)).json()[0]["id"]
            body = (await client.get(f"/api/v1/analytics/portfolio/{portfolio_id}", headers=headers)).json()
        assert body["total_gain_loss"] == pytest.approx(EXPECTED_GAIN)

    async def test_report_platforms_and_portfolios_add_up_to_the_account_gain(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, _auth(regular_user))
            data = await ReportDataMixin().get_report_data(db_session, str(regular_user.id))
        assert sum(row["net_pnl"] for row in data["platform_analysis"]) == pytest.approx(EXPECTED_GAIN)
        assert [summary.gain_loss for summary in data["portfolios"]] == pytest.approx([EXPECTED_GAIN])

    async def test_sold_out_position_bears_its_foreign_fee(
        self,
        client: AsyncClient,
        regular_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def half(self: RateResolver, from_currency: str, to_currency: str) -> float:
            return 0.5

        monkeypatch.setattr(RateResolver, "tracked_rate", half)
        headers = _auth(regular_user)
        portfolio = await client.post("/api/v1/portfolios", json={"name": "Frais"}, headers=headers)
        portfolio_id = portfolio.json()["id"]
        asset = await client.post(
            "/api/v1/assets",
            json={"portfolio_id": portfolio_id, "symbol": "SOL", "asset_type": "crypto", "exchange": "Kraken"},
            headers=headers,
        )
        moves = [
            ("buy", "100", "10", "USD", "2026-01-01T10:00:00Z"),
            ("sell", "200", "0", None, "2026-02-01T10:00:00Z"),
        ]
        for kind, price, fee, fee_currency, moment in moves:
            body = {
                "asset_id": asset.json()["id"],
                "transaction_type": kind,
                "quantity": "1",
                "price": price,
                "fee": fee,
                "fee_currency": fee_currency,
                "currency": "EUR",
                "executed_at": moment,
                "exchange": "Kraken",
            }
            response = await client.post("/api/v1/transactions", json=body, headers=headers)
            assert response.status_code == 201, response.text
        history = (await client.get(f"{BASE}/portfolio/{portfolio_id}/history", headers=headers)).json()
        assert history["realized_gains"] == pytest.approx(95.0)


def test_platform_pnl_adds_realized_gain_and_keeps_sold_out_platforms() -> None:
    position = SimpleNamespace(exchange="Kraken", current_value=150.0, total_invested=100.0, total_fees=1.0)
    sales = {"Kraken": {"realized": 25.0, "cost_sold": 100.0}, "Binance": {"realized": 40.0, "cost_sold": 80.0}}
    rows = {row["exchange"]: row for row in platform_analysis([position], sales)}
    assert rows["Kraken"]["net_pnl"] == pytest.approx(75.0)
    assert rows["Kraken"]["roi_percent"] == pytest.approx(37.5)
    assert rows["Binance"]["net_pnl"] == pytest.approx(40.0)
    assert rows["Binance"]["roi_percent"] == pytest.approx(50.0)
    assert rows["Binance"]["count"] == 0


def test_a_stored_snapshot_no_longer_carries_a_gain() -> None:
    snapshot = SimpleNamespace(
        snapshot_date=datetime(2026, 1, 1, tzinfo=UTC), total_value=Decimal("120"), total_invested=Decimal("100")
    )
    assert _snapshot_point(snapshot, 30)["gain_loss"] is None
