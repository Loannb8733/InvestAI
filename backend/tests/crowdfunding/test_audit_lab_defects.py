import pymupdf
import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from tests.crowdfunding.recorder import BASE
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "no_llm")

PROJECT = {
    "platform": "Anaxago",
    "project_name": "Résidence des Tilleuls",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 24,
    "start_date": "2025-10-01",
    "estimated_end_date": "2027-10-01",
}


def _deck() -> list[tuple[str, tuple[str, bytes, str]]]:
    doc = pymupdf.open()
    page = doc.new_page()
    for row, line in enumerate(("TRI cible : 9,5 %", "Montant de la collecte : 800 000 €", "LTV : 65 %")):
        page.insert_text((72, 72 + 18 * row), line)
    data: bytes = doc.tobytes()
    doc.close()
    return [("files", ("deck.pdf", data, "application/pdf"))]


async def _setup(client: AsyncClient, db: AsyncSession, user: User) -> tuple[dict[str, str], str]:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    await seed_history(db)
    await seed_portfolio(client, headers)
    project = await client.post(BASE, headers=headers, json=PROJECT)
    return headers, project.json()["id"]


async def test_uploading_documents_audits_them(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers, project_id = await _setup(client, db_session, regular_user)
        documents = (await client.post(f"{BASE}/{project_id}/documents", headers=headers, files=_deck())).json()
        audits = (await client.get(f"{BASE}/audits", headers=headers)).json()
    assert [audit["project_id"] for audit in audits] == [project_id]
    assert documents[0]["audit_id"] == audits[0]["id"]


async def test_audit_values_the_portfolio_like_the_dashboard(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers, _ = await _setup(client, db_session, regular_user)
        audit = (await client.post(f"{BASE}/analyze", headers=headers, files=_deck())).json()
    ticket = audit["suggested_investment"]
    share = audit["portfolio_concentration"]["asset_type"]["score"]
    assert ticket == 920.0
    assert share == round((1000 + ticket) / (63600 + 1840 + 1000 + ticket), 2)
