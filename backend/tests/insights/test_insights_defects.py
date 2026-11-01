from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.service import analytics_service
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.insights.anomalies import anomaly_impacts
from app.domains.market_data.history import reader
from app.domains.predictions.service import prediction_service
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import ASSETS, FROZEN_NOW, seed_history, seed_portfolio

INSIGHTS = "/api/v1/insights"
SMART = "/api/v1/smart-insights"
EXCHANGES = {symbol: exchange for symbol, _, exchange, _ in ASSETS}


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _transaction(client: AsyncClient, headers: dict[str, str], symbol: str, **fields: Any) -> None:
    assets = (await client.get("/api/v1/assets", headers=headers)).json()
    asset_id = next(asset["id"] for asset in assets if asset["symbol"] == symbol)
    body = {
        "asset_id": asset_id,
        "fee": "0",
        "currency": "EUR",
        "executed_at": "2026-09-20T10:00:00Z",
        "exchange": EXCHANGES[symbol],
        **fields,
    }
    response = await client.post("/api/v1/transactions", json=body, headers=headers)
    assert response.status_code == 201, response.text


@pytest.fixture
def isolated_insights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "session_factory", TestSessionLocal)


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster", "isolated_insights")
class TestSeededAccount:
    @pytest.fixture
    async def headers(self, client: AsyncClient, db_session: AsyncSession, regular_user: User) -> dict[str, str]:
        auth = _auth(regular_user)
        with time_machine.travel(FROZEN_NOW, tick=False):
            await seed_history(db_session)
            await seed_portfolio(client, auth)
        return auth

    @staticmethod
    async def _get(client: AsyncClient, url: str, headers: dict[str, str]) -> Any:
        with time_machine.travel(FROZEN_NOW, tick=False):
            response = await client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    async def test_backtest_invests_every_month_since_the_start(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        body = await self._get(client, f"{INSIGHTS}/backtest-dca?symbol=BTC&start_year=2026&start_month=1", headers)
        assert body["nb_months"] == 10
        assert body["total_invested"] == 1000
        assert body["start_date"] == "2026-01"

    async def test_backtest_start_date_is_the_first_month_actually_bought(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        body = await self._get(client, f"{INSIGHTS}/backtest-dca?symbol=BTC", headers)
        assert body["start_date"] == body["monthly_history"][0]["month"]
        assert body["start_date"] > "2020-01"

    async def test_backtest_rejects_an_unknown_asset_type(self, client: AsyncClient, headers: dict[str, str]) -> None:
        response = await client.get(f"{INSIGHTS}/backtest-dca?symbol=BTC&asset_type=nimporte", headers=headers)
        assert response.status_code == 422

    async def test_passive_income_counts_dividends_and_interest(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        await _transaction(client, headers, "AAPL", transaction_type="dividend", quantity="1", price="20")
        await _transaction(client, headers, "DOGE", transaction_type="interest", quantity="100", price="0.15")
        body = await self._get(client, f"{INSIGHTS}/passive-income", headers)
        assert body["by_type"] == {"dividend": 20.0, "interest": 15.0}
        assert body["total_income"] == 35.0

    async def test_passive_income_flags_a_reward_without_price(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        await _transaction(client, headers, "ETH", transaction_type="staking_reward", quantity="0.01", price="0")
        body = await self._get(client, f"{INSIGHTS}/passive-income", headers)
        assert body["nb_sans_cours"] == 1
        assert body["by_month"] == {}

    async def test_a_one_off_airdrop_is_not_projected_over_the_year(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        await _transaction(client, headers, "UNI", transaction_type="airdrop", quantity="5", price="8")
        await _transaction(client, headers, "ETH", transaction_type="staking_reward", quantity="0.01", price="1000")
        body = await self._get(client, f"{INSIGHTS}/passive-income", headers)
        assert body["total_income"] == 50.0
        assert body["projected_annual"] == 120.0

    async def test_fees_count_fee_transactions(self, client: AsyncClient, headers: dict[str, str]) -> None:
        before = await self._get(client, f"{INSIGHTS}/fees", headers)
        await _transaction(client, headers, "UNI", transaction_type="fee", quantity="1", price="9")
        after = await self._get(client, f"{INSIGHTS}/fees", headers)
        assert after["total_fees"] == before["total_fees"] + 9
        assert after["by_type"]["fee"] == 9

    async def test_foreign_fee_without_rate_is_not_marked_converted(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        await _transaction(
            client,
            headers,
            "SOL",
            transaction_type="buy",
            quantity="1",
            price="140",
            fee="2",
            fee_currency="USD",
            currency="USD",
        )
        body = await self._get(client, f"{INSIGHTS}/fees", headers)
        assert body["nb_frais_non_convertis"] == 1

    async def test_tax_loss_leaves_stablecoins_out_and_uses_fifo_cost(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        body = await self._get(client, f"{INSIGHTS}/tax-loss-harvesting", headers)
        assert [entry["symbol"] for entry in body["opportunities"]] == ["ARB"]
        assert body["opportunities"][0]["cost_basis"] == 1201.0
        assert body["total_harvestable"] == -401.0

    async def test_tax_saving_is_capped_by_this_year_realized_gains(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        body = await self._get(client, f"{INSIGHTS}/tax-loss-harvesting", headers)
        assert body["realized_gains_this_year"] == 1496.0
        assert body["estimated_tax_saving"] == pytest.approx(401 * 0.30)
        await _transaction(
            client,
            headers,
            "BTC",
            transaction_type="sell",
            quantity="0.5",
            price="10000",
            executed_at="2026-09-20T10:00:00Z",
        )
        body = await self._get(client, f"{INSIGHTS}/tax-loss-harvesting", headers)
        assert body["realized_gains_this_year"] < 0
        assert body["estimated_tax_saving"] == 0
        assert body["opportunities"][0]["potential_tax_saving"] == 0

    async def test_tax_note_does_not_quote_an_american_rule(self, client: AsyncClient, headers: dict[str, str]) -> None:
        body = await self._get(client, f"{INSIGHTS}/tax-loss-harvesting", headers)
        assert "wash sale" not in body["note"]

    async def test_sharpe_is_measured_over_at_least_three_months(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        week = await self._get(client, f"{SMART}/health?days=7", headers)
        quarter = await self._get(client, f"{SMART}/health?days=90", headers)
        assert week["metrics_summary"]["sharpe_ratio"] == quarter["metrics_summary"]["sharpe_ratio"]
        assert abs(week["metrics_summary"]["sharpe_ratio"]) < 50

    async def test_var_is_never_negative(self, client: AsyncClient, headers: dict[str, str]) -> None:
        body = await self._get(client, f"{SMART}/health?days=7", headers)
        assert body["metrics_summary"]["var_95"] >= 0

    async def test_summary_runs_the_analysis_once(
        self, client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = analytics_service.get_user_analytics
        windows: list[int] = []

        async def spy(db: AsyncSession, user_id: str, **kwargs: Any) -> Any:
            windows.append(kwargs["days"])
            return await original(db, user_id, **kwargs)

        monkeypatch.setattr(analytics_service, "get_user_analytics", spy)
        await self._get(client, f"{SMART}/health?days=90", headers)
        health_calls = len(windows)
        windows.clear()
        body = await self._get(client, f"{SMART}/summary?days=90", headers)
        assert len(windows) == health_calls
        assert body["breakeven_pct"] is not None

    async def test_anomalies_route_does_not_build_the_whole_report(
        self, client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        async def recorded(_db: AsyncSession, user_id: str, **_kwargs: Any) -> Any:
            calls.append(user_id)
            raise RuntimeError("analyse indisponible")

        monkeypatch.setattr(analytics_service, "get_user_analytics", recorded)
        await self._get(client, f"{SMART}/anomalies-impact", headers)
        assert calls == []

    async def test_a_failed_diversification_still_answers(
        self, client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def failure(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("analyse indisponible")

        monkeypatch.setattr(analytics_service, "get_diversification_analysis", failure)
        body = await self._get(client, f"{SMART}/health", headers)
        assert body["metrics_summary"]["hhi"] is None

    async def test_diversification_follows_the_requested_period(
        self, client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = analytics_service.get_diversification_analysis
        windows: list[int] = []

        async def spy(db: AsyncSession, user_id: str, **kwargs: Any) -> Any:
            windows.append(kwargs["days"])
            return await original(db, user_id, **kwargs)

        monkeypatch.setattr(analytics_service, "get_diversification_analysis", spy)
        await self._get(client, f"{SMART}/health?days=30", headers)
        assert windows == [30]


@pytest.mark.usefixtures("empty_test_redis", "offline", "deterministic_forecaster", "isolated_insights")
class TestEmptyAccount:
    async def test_an_empty_account_gets_no_grade(self, client: AsyncClient, regular_user: User) -> None:
        body = (await client.get(f"{SMART}/health", headers=_auth(regular_user))).json()
        assert body["overall_status"] == "unknown"
        assert body["overall_score"] == 0
        assert [insight["title"] for insight in body["insights"]] == ["Portefeuille vide"]

    async def test_empty_fees_have_every_field(self, client: AsyncClient, regular_user: User) -> None:
        body = (await client.get(f"{INSIGHTS}/fees", headers=_auth(regular_user))).json()
        assert body["nb_frais_non_convertis"] == 0

    async def test_empty_tax_loss_has_every_field(self, client: AsyncClient, regular_user: User) -> None:
        body = (await client.get(f"{INSIGHTS}/tax-loss-harvesting", headers=_auth(regular_user))).json()
        assert body["nb_candidates"] == 0
        assert body["realized_gains_this_year"] == 0
        assert "note" in body

    async def test_empty_income_has_every_field(self, client: AsyncClient, regular_user: User) -> None:
        body = (await client.get(f"{INSIGHTS}/passive-income", headers=_auth(regular_user))).json()
        assert body["nb_sans_cours"] == 0


async def test_a_stablecoin_move_is_not_an_anomaly(
    db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    detected = [
        SimpleNamespace(
            symbol="USDC",
            is_anomaly=True,
            anomaly_type="spike",
            severity="low",
            description="z-score",
            price_change_percent=0.1,
            detected_at=datetime(2026, 1, 1),
        )
    ]

    async def detect(*_args: Any) -> Any:
        return detected

    monkeypatch.setattr(prediction_service, "detect_anomalies", detect)
    assert await anomaly_impacts(db_session, str(regular_user.id)) == []
