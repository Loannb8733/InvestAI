import json

import pymupdf
import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.services.ai.crowdfunding_analyzer import crowdfunding_analyzer
from tests.crowdfunding.recorder import BASE, UNKNOWN_ID, Recorder
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

PROJECT = {
    "platform": "Anaxago",
    "project_name": "Résidence des Tilleuls",
    "invested_amount": "1000",
    "annual_rate": "10",
    "duration_months": 24,
    "start_date": "2025-10-01",
    "estimated_end_date": "2027-10-01",
}
DECK = (
    "Projet Résidence des Tilleuls - Lyon",
    "TRI cible : 9,5 %",
    "Durée : 18 à 24 mois",
    "Montant de la collecte : 800 000 €",
    "LTV : 65 %",
    "Marge brute : 12 %",
    "Pré-commercialisation : 40 %",
)
LLM_ANSWER = {
    "project_name": "Les Tilleuls",
    "operator": "Promoteur Rhône",
    "location": "Lyon 7e",
    "document_type": "deck",
    "tri": 11,
    "duration_min": 18,
    "duration_max": 24,
    "collection_amount": 800000,
    "margin_percent": 8,
    "ltv": 85,
    "pre_sales_percent": 0,
    "guarantees": [{"type": "Hypothèque", "rank": "2ème rang", "description": "Sur le terrain", "strength": "faible"}],
    "risk_score": 4,
    "points_forts": ["Emplacement"],
    "red_flags": [],
    "verdict": "INVESTIR",
}


def _pdf(*lines: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for row, line in enumerate(lines):
        page.insert_text((72, 72 + 18 * row), line)
    data: bytes = doc.tobytes()
    doc.close()
    return data


DECK_PDF = _pdf(*DECK)


def _files(*names: str, content: bytes | None = None) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, content if content is not None else DECK_PDF, "application/pdf")) for name in names]


@pytest.fixture
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_URL"):
        monkeypatch.setattr(settings, key, "")


@pytest.fixture
def scripted_llm(no_llm: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def answer(messages: list[dict[str, str]]) -> str:
        return json.dumps(LLM_ANSWER)

    monkeypatch.setattr(settings, "GROQ_API_KEY", "cle-de-test")
    monkeypatch.setattr(crowdfunding_analyzer, "_call_groq", answer)


async def _setup(client: AsyncClient, db_session: AsyncSession, headers: dict[str, str]) -> str:
    await seed_history(db_session)
    await seed_portfolio(client, headers)
    created = await client.post(BASE, headers=headers, json=PROJECT)
    project_id: str = created.json()["id"]
    return project_id


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "no_llm")
async def test_static_analysis_matches_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    rec = Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project_id = await _setup(client, db_session, headers)
        await rec.shot("audits_empty", "GET", f"{BASE}/audits", headers)
        form = {"project_id": project_id}
        await rec.shot("analyze_static", "POST", f"{BASE}/analyze", headers, files=_files("deck.pdf"), data=form)
        text = [("files", ("notes.txt", b"pas un pdf", "text/plain"))]
        await rec.shot("analyze_not_pdf", "POST", f"{BASE}/analyze", headers, files=text)
        many = _files(*(f"deck{i}.pdf" for i in range(6)))
        await rec.shot("analyze_too_many", "POST", f"{BASE}/analyze", headers, files=many)
        await rec.shot("analyze_no_file", "POST", f"{BASE}/analyze", headers)
        await rec.shot("audits_after_analyze", "GET", f"{BASE}/audits", headers)
    assert not rec.mismatches, f"golden crowdfunding différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "scripted_llm")
async def test_llm_analysis_matches_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project_id = await _setup(client, db_session, headers)
        url = f"{BASE}/analyze?project_id={project_id}"
        await rec.shot("analyze_llm", "POST", url, headers, files=_files("deck.pdf"))
        await rec.shot("analyze_other_user_project", "POST", url, other, files=_files("deck.pdf"))
        blank = _files("vide.pdf", content=_pdf())
        await rec.shot("analyze_blank_pdf", "POST", f"{BASE}/analyze", headers, files=blank)
        await rec.shot("audits_other_user", "GET", f"{BASE}/audits", other)
    assert not rec.mismatches, f"golden crowdfunding différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"


@pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "no_llm")
async def test_project_documents_match_golden(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, admin_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    other = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    rec = Recorder(client)
    with time_machine.travel(FROZEN_NOW, tick=False):
        project_id = await _setup(client, db_session, headers)
        docs_url = f"{BASE}/{project_id}/documents"
        uploaded = await rec.shot("upload", "POST", docs_url, headers, files=_files("deck.pdf", 'fici "v2".pdf'))
        await rec.shot("upload_not_pdf", "POST", docs_url, headers, files=[("files", ("a.docx", b"x", "text/plain"))])
        await rec.shot("upload_too_many", "POST", docs_url, headers, files=_files(*(f"d{i}.pdf" for i in range(6))))
        await rec.shot(
            "upload_unknown_project", "POST", f"{BASE}/{UNKNOWN_ID}/documents", headers, files=_files("d.pdf")
        )
        await rec.shot("upload_other_user", "POST", docs_url, other, files=_files("d.pdf"))
        await rec.shot("project_with_documents", "GET", f"{BASE}/{project_id}", headers)
        await rec.shot("audits_after_upload", "GET", f"{BASE}/audits", headers)
        for index, doc in enumerate(uploaded):
            response = await client.get(f"{BASE}/documents/{doc['id']}/download", headers=headers)
            rec.compare(
                f"download_{index}",
                {
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "disposition": response.headers.get("content-disposition"),
                    "same_bytes": response.content == DECK_PDF,
                },
            )
        first = f"{BASE}/documents/{uploaded[0]['id']}/download"
        await rec.shot("download_other_user", "GET", first, other)
        await rec.shot("download_unknown", "GET", f"{BASE}/documents/{UNKNOWN_ID}/download", headers)
    assert not rec.mismatches, f"golden crowdfunding différent : {rec.mismatches} (GOLDEN_UPDATE=1 pour accepter)"
