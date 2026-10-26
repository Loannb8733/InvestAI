from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.main import app
from app.models.calendar_event import CalendarEvent
from tests.crowdfunding.recorder import BASE
from tests.sample_portfolio import FROZEN_NOW

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")

QUARTERLY = {
    "platform": "Anaxago",
    "project_name": "Résidence des Tilleuls",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 24,
    "start_date": "2025-10-01",
    "estimated_end_date": "2027-10-01",
    "interest_frequency": "quarterly",
}
AMORTIZABLE = {
    "platform": "Homunity",
    "project_name": "Bureaux",
    "invested_amount": "1200",
    "annual_rate": "10",
    "duration_months": 12,
    "repayment_type": "amortizable",
    "start_date": "2026-01-15",
    "tax_rate": "0",
}


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _create(client: AsyncClient, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(BASE, headers=headers, json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_creation_keeps_tax_rate_and_delay(client: AsyncClient, regular_user: User) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, _headers(regular_user), {**QUARTERLY, "tax_rate": "12.8", "delay_months": 3})
    assert (project["tax_rate"], project["delay_months"]) == (12.8, 3)
    assert project["schedule"][0]["expected_interest"] == 21.8
    assert project["schedule"][-1]["due_date"] == "2028-01-01"


async def test_patch_carries_amount_and_name_to_the_asset(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, QUARTERLY)
        patch = {"invested_amount": "1200", "project_name": "Les Tilleuls"}
        await client.patch(f"{BASE}/{project['id']}", headers=headers, json=patch)
        asset = (await client.get(f"/api/v1/assets/{project['asset_id']}", headers=headers)).json()
    assert (asset["invested_amount"], asset["avg_buy_price"]) == (1200.0, 1200.0)
    assert (asset["name"], asset["symbol"]) == ("Les Tilleuls", "ANAXAGO-LES TILLEULS")


async def test_amortizable_interest_runs_on_outstanding_capital(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, AMORTIZABLE)
        stress = (await client.get(f"{BASE}/{project['id']}/stress-test", headers=headers)).json()
    interests = [entry["expected_interest"] for entry in project["schedule"]]
    assert (interests[0], interests[-1]) == (10.0, 0.83)
    assert stress["base_irr"] == pytest.approx(10.5, abs=0.1)


async def test_in_fine_last_partial_period_carries_capital(client: AsyncClient, regular_user: User) -> None:
    body = {**QUARTERLY, "annual_rate": "12", "duration_months": 18, "interest_frequency": "annual", "tax_rate": "0"}
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, _headers(regular_user), {**body, "start_date": "2024-01-01"})
    schedule = [(e["due_date"], e["expected_capital"], e["expected_interest"]) for e in project["schedule"]]
    assert schedule == [("2025-01-01", 0.0, 120.0), ("2025-07-01", 1000.0, 60.0)]


async def test_calendar_follows_the_contractual_schedule(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, _headers(regular_user), QUARTERLY)
    rows = await db_session.execute(
        select(CalendarEvent.__table__.c.event_date, CalendarEvent.__table__.c.amount).order_by(
            CalendarEvent.__table__.c.event_date
        )
    )
    events = [(when.date().isoformat(), float(amount)) for when, amount in rows.all()]
    upcoming = [(e["due_date"], e["expected_capital"] + e["expected_interest"]) for e in project["schedule"]]
    assert events == [entry for entry in upcoming if entry[0] >= FROZEN_NOW.date().isoformat()]
    assert events[-1] == ("2027-10-01", 1017.5)


async def test_cashflow_schedule_is_documented_as_net(client: AsyncClient, regular_user: User) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _create(client, _headers(regular_user), QUARTERLY)
        months = (await client.get(f"{BASE}/cashflow-schedule", headers=_headers(regular_user))).json()
    description = app.openapi()["components"]["schemas"]["CashflowMonthResponse"]["description"]
    assert months[0]["expected_interest"] == 17.5
    assert "nets" in description
    assert "brut" not in description.lower()


async def test_referral_does_not_settle_an_installment(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, AMORTIZABLE)
        bonus = {"payment_date": "2026-03-20", "amount": "10", "payment_type": "referral"}
        await client.post(f"{BASE}/{project['id']}/repayments", headers=headers, json=bonus)
        schedule = (await client.get(f"{BASE}/{project['id']}", headers=headers)).json()["schedule"]
    assert not [entry for entry in schedule if entry["is_completed"]]


async def test_dashboard_net_interest_deducts_withholding(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, QUARTERLY)
        coupon = {"payment_date": "2026-01-02", "amount": "25", "payment_type": "interest", "tax_amount": "3.2"}
        await client.post(f"{BASE}/{project['id']}/repayments", headers=headers, json=coupon)
        dashboard = (await client.get(f"{BASE}/dashboard", headers=headers)).json()
        report = (await client.get(f"{BASE}/tax-report", headers=headers)).json()
    assert dashboard["total_interest_net"] == report["total_net_interest"] == 21.8


async def test_completing_a_project_keeps_recorded_interest(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, AMORTIZABLE)
        split = {"payment_date": "2026-02-16", "amount": "110", "payment_type": "both"}
        split |= {"capital_amount": "100", "interest_amount": "10"}
        await client.post(f"{BASE}/{project['id']}/repayments", headers=headers, json=split)
        patched = (await client.patch(f"{BASE}/{project['id']}", headers=headers, json={"status": "completed"})).json()
        fetched = (await client.get(f"{BASE}/{project['id']}", headers=headers)).json()
    assert patched["interest_earned"] == fetched["interest_earned"] == 10.0


async def test_defaulted_project_is_never_on_track(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    body = {**QUARTERLY, "start_date": "2024-01-01", "estimated_end_date": "2025-01-01", "duration_months": 12}
    with time_machine.travel(FROZEN_NOW, tick=False):
        project = await _create(client, headers, {**body, "interest_frequency": "at_maturity", "status": "defaulted"})
        coupon = {"payment_date": "2025-01-02", "amount": "70", "payment_type": "interest"}
        await client.post(f"{BASE}/{project['id']}/repayments", headers=headers, json=coupon)
        rows = (await client.get(f"{BASE}/performance", headers=headers)).json()["projects"]
    assert rows[0]["status"] == "defaulted"
    assert rows[0]["on_track"] is False


async def test_unknown_interest_frequency_is_rejected(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        created = await client.post(BASE, headers=headers, json={**QUARTERLY, "interest_frequency": "weekly"})
        project = await _create(client, headers, {**QUARTERLY, "project_name": "Lofts"})
        patched = await client.patch(f"{BASE}/{project['id']}", headers=headers, json={"interest_frequency": "daily"})
    assert (created.status_code, patched.status_code) == (422, 422)


async def test_another_users_portfolio_is_not_found(client: AsyncClient, regular_user: User, admin_user: User) -> None:
    portfolios = (await client.get("/api/v1/portfolios", headers=_headers(admin_user))).json()
    target = portfolios[0]["id"] if portfolios else None
    if target is None:
        target = (await client.post("/api/v1/portfolios", headers=_headers(admin_user), json={"name": "Perso"})).json()[
            "id"
        ]
    response = await client.post(BASE, headers=_headers(regular_user), json={**QUARTERLY, "portfolio_id": target})
    assert response.status_code == 404


async def test_projects_sharing_a_symbol_prefix_get_distinct_symbols(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        first = await _create(client, headers, QUARTERLY)
        second = await _create(client, headers, {**QUARTERLY, "project_name": "Résidence des Lilas"})
        third = await _create(client, headers, {**QUARTERLY, "project_name": "Lofts"})
        renamed = await client.patch(
            f"{BASE}/{third['id']}", headers=headers, json={"project_name": "Résidence des Roses"}
        )
        symbols = [
            (await client.get(f"/api/v1/assets/{project['asset_id']}", headers=headers)).json()["symbol"]
            for project in (first, second, third)
        ]
    assert renamed.status_code == 200
    assert symbols == ["ANAXAGO-RÉSIDENCE DE", "ANAXAGO-RÉSIDENCE-2", "ANAXAGO-RÉSIDENCE-3"]
