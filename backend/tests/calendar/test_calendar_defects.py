from decimal import Decimal
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.fx.spot import spot_rates
from tests.sample_portfolio import FROZEN_NOW

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline")
BASE = "/api/v1/calendar"
RENT = {
    "title": "Loyer T2",
    "event_type": "rent",
    "event_date": "2026-10-05T09:00:00Z",
    "amount": 800,
    "is_recurring": True,
    "recurrence_rule": "FREQ=MONTHLY",
}
PROJECT = {
    "platform": "Anaxago",
    "project_name": "Lofts",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 12,
    "start_date": "2026-06-01",
    "estimated_end_date": "2027-06-01",
    "interest_frequency": "quarterly",
}


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _create(client: AsyncClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    response = await client.post(BASE, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_completing_a_recurring_event_twice_creates_one_next_occurrence(
    client: AsyncClient, regular_user: User
) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        rent = await _create(client, headers, **RENT)
        await client.post(f"{BASE}/{rent['id']}/complete", headers=headers)
        again = await client.post(f"{BASE}/{rent['id']}/complete", headers=headers)
        events = (await client.get(f"{BASE}?event_type=rent", headers=headers)).json()
    assert again.status_code == 200
    assert [(e["event_date"], e["is_completed"]) for e in events] == [
        ("2026-10-05T09:00:00Z", True),
        ("2026-11-05T09:00:00Z", False),
    ]


async def test_yearly_event_on_february_29_moves_to_february_28(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    body = {**RENT, "event_type": "dividend", "event_date": "2028-02-29T09:00:00Z", "recurrence_rule": "YEARLY"}
    with time_machine.travel(FROZEN_NOW, tick=False):
        leap = await _create(client, headers, **body)
        completed = await client.post(f"{BASE}/{leap['id']}/complete", headers=headers)
        events = (await client.get(BASE, headers=headers)).json()
    assert completed.status_code == 200
    assert [e["event_date"] for e in events] == ["2028-02-29T09:00:00Z", "2029-02-28T09:00:00Z"]


async def test_summary_counts_every_occurrence_of_recurring_income(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _create(client, headers, **RENT)
        summary = (await client.get(f"{BASE}/summary", headers=headers)).json()
        passive = (await client.get(f"{BASE}/passive-income", headers=headers)).json()
    assert (summary["total_expected_income"], summary["projected_income_this_month"]) == (8800.0, 800.0)
    assert passive["total_12m"] == summary["total_expected_income"]


async def test_zero_amount_is_returned_as_zero(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        created = await _create(
            client, headers, title="Nul", event_type="payment_due", event_date=RENT["event_date"], amount=0
        )
    assert created["amount"] == 0.0


async def test_patch_clears_optional_fields_and_refuses_required_ones(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        rent = await _create(client, headers, **RENT, description="Appartement")
        url = f"{BASE}/{rent['id']}"
        cleared = await client.patch(url, headers=headers, json={"description": None, "amount": None})
        refused = await client.patch(url, headers=headers, json={"title": None})
    assert (cleared.json()["description"], cleared.json()["amount"]) == (None, None)
    assert cleared.json()["title"] == "Loyer T2"
    assert refused.status_code == 422


async def test_tax_deadlines_name_the_income_year_and_are_not_doubled(client: AsyncClient, regular_user: User) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        old_title = "Ouverture de la déclaration des revenus 2027"
        await _create(client, headers, title=old_title, event_type="tax_deadline", event_date="2027-04-01T09:00:00Z")
        seeded = (await client.post(f"{BASE}/seed-tax-events", headers=headers)).json()
        events = (await client.get(f"{BASE}?event_type=tax_deadline", headers=headers)).json()
    assert (seeded["created"], seeded["skipped"]) == (2, 4)
    assert [e["title"] for e in events] == [
        old_title,
        "Date limite de la déclaration en ligne 2027 des revenus 2026 (départements 50 et +)",
        "Solde de l'impôt sur les revenus 2026",
    ]


async def test_passive_income_counts_crowdfunding_interest_without_capital(
    client: AsyncClient, regular_user: User
) -> None:
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await client.post("/api/v1/crowdfunding", headers=headers, json=PROJECT)
        passive = (await client.get(f"{BASE}/passive-income", headers=headers)).json()
        summary = (await client.get(f"{BASE}/summary", headers=headers)).json()
    june = next(month["amount"] for month in passive["monthly"] if month["month"] == "2027-06")
    assert (june, passive["sources"]["crowdfunding"], summary["total_expected_income"]) == (17.5, 52.5, 52.5)


async def test_income_without_exchange_rate_is_left_out_and_named(
    client: AsyncClient, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_rate(from_ccy: str, to_ccy: str) -> Decimal | None:
        return Decimal("1") if from_ccy.upper() == to_ccy.upper() else None

    monkeypatch.setattr(spot_rates, "get", no_rate)
    headers = _headers(regular_user)
    with time_machine.travel(FROZEN_NOW, tick=False):
        when = "2026-12-01T09:00:00Z"
        await _create(
            client, headers, title="Coupon US", event_type="interest", event_date=when, amount=100, currency="USD"
        )
        await _create(client, headers, title="Coupon FR", event_type="interest", event_date=when, amount=50)
        passive = (await client.get(f"{BASE}/passive-income", headers=headers)).json()
        summary = (await client.get(f"{BASE}/summary", headers=headers)).json()
    assert (passive["total_12m"], passive["unconverted_currencies"]) == (50.0, ["USD"])
    assert (summary["total_expected_income"], summary["unconverted_currencies"]) == (50.0, ["USD"])
