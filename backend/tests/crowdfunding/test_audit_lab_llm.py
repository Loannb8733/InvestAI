"""L'Audit Lab analysait sans IA en production depuis le retrait de son modèle Groq, sans que rien ne le signale.

Constaté le 2026-11-17 : `llama-3.1-8b-instant` rendait une 404, la cascade retombait sur l'extraction statique
à chaque audit. Le palier gratuit de Groq plafonne à 8 000 tokens par minute, réponse comprise : un vrai dossier
doit être réduit à ses pages utiles. Sur six vrais dossiers, le prompt faisait aussi inventer des zéros
(pré-commercialisation, marge) et des alertes contredites par les garanties extraites.
"""

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.domains.crowdfunding.audit import providers
from app.domains.crowdfunding.audit.page_selection import PAGE_SEPARATOR, PROMPT_BUDGET_CHARS, select_pages
from app.domains.crowdfunding.audit.prompt import ANALYSIS_SCHEMA, SYSTEM_PROMPT
from app.domains.crowdfunding.audit.scoring import add_red_flags
from app.domains.crowdfunding.audit.static import analyze_statically
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token

MARKET = "Analyse de marché. Le taux de vacance est de 2 %, le taux de chômage de 7 %, le taux d'emploi monte. " * 12


def _answer(status: int, body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", providers.GROQ_URL))


class _FakePost:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.payloads: list[dict[str, Any]] = []

    async def __call__(self, name: str, url: str, payload: dict[str, Any], headers: Any = None) -> httpx.Response:
        self.payloads.append(payload)
        return self.responses.pop(0)


OK = {"choices": [{"message": {"content": '{"verdict": "VIGILANCE"}'}}]}
GONE = {
    "error": {"message": "The model `x` does not exist or you do not have access to it.", "code": "model_not_found"}
}


async def test_groq_uses_a_current_model_with_room_for_the_free_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _FakePost(_answer(200, OK))
    monkeypatch.setattr(providers, "_post", post)
    await providers.call_groq([{"role": "user", "content": "dossier"}])
    payload = post.payloads[0]
    assert payload["model"] == settings.GROQ_MODEL == "openai/gpt-oss-120b"
    assert payload["max_tokens"] <= 2000
    assert payload["reasoning_effort"] == "low"


async def test_a_retired_groq_model_falls_back_to_the_second_one(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _FakePost(_answer(404, GONE), _answer(200, OK))
    monkeypatch.setattr(providers, "_post", post)
    raw = await providers.call_groq([{"role": "user", "content": "dossier"}])
    assert [p["model"] for p in post.payloads] == [settings.GROQ_MODEL, settings.GROQ_FALLBACK_MODEL]
    assert "reasoning_effort" not in post.payloads[1]
    assert raw == '{"verdict": "VIGILANCE"}'


def test_page_selection_keeps_the_key_pages_over_repeated_market_words() -> None:
    fici = ["Durée : 18 mois. Taux d'intérêt : 11 %.", "Garanties : hypothèque de premier rang, caution personnelle."]
    pages = PAGE_SEPARATOR.join([*fici, *[MARKET] * 30, "Permis de construire purgé de tout recours."])
    kept = select_pages([pages])[0]
    assert all(page in kept for page in fici)
    assert "purgé" in kept
    assert len(kept) <= PROMPT_BUDGET_CHARS


def test_a_short_dossier_is_sent_whole() -> None:
    texts = ["Page unique : TRI 10 %, collecte 500 000 €."]
    assert select_pages(texts) == texts


def test_the_prompt_no_longer_turns_missing_values_into_zeros() -> None:
    assert "0 si non mentionné" not in ANALYSIS_SCHEMA["pre_sales_percent"]
    assert "null" in SYSTEM_PROMPT
    assert "français" in SYSTEM_PROMPT


def test_static_extraction_leaves_unknown_pre_sales_empty() -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "TRI cible : 9,5 % - Montant de la collecte : 800 000 €")
    data = analyze_statically([("deck.pdf", doc.tobytes())])
    doc.close()
    assert data["pre_sales_percent"] is None


def test_alerts_follow_the_extracted_facts_not_the_model() -> None:
    data = {
        "guarantees": [{"type": "Hypothèque conventionnelle", "rank": "premier rang"}],
        "margin_percent": None,
        "pre_sales_percent": None,
        "admin_status": "PC purgé",
        "red_flags": ["Pas d'hypothèque de 1er rang", "Marge < 10%", "Pré-commercialisation = 0%", "Opérateur récent"],
        "verdict": "VIGILANCE",
    }
    result = add_red_flags(data)
    assert result["red_flags"] == ["Opérateur récent"]
    assert any("marge" in point.lower() for point in result["points_vigilance"])


def test_no_guarantee_at_all_is_an_alert() -> None:
    result = add_red_flags({"guarantees": [], "red_flags": [], "verdict": "INVESTIR"})
    assert any("garantie" in flag.lower() for flag in result["red_flags"])


def test_a_permit_still_under_review_is_an_alert() -> None:
    result = add_red_flags({"guarantees": [{"type": "Hypothèque", "rank": "1er rang"}], "admin_status": "PC en cours"})
    assert any("permis" in flag.lower() for flag in result["red_flags"])


async def _groq_status_offering(monkeypatch: pytest.MonkeyPatch, offered: list[str]) -> providers.ProviderStatus:
    monkeypatch.setattr(settings, "GROQ_API_KEY", "cle-de-test")

    async def models(name: str, url: str, headers: Any = None) -> httpx.Response:
        body = {"data": [{"id": model} for model in offered]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(providers, "_get", models)
    return next(p for p in await providers.provider_status() if p.name == "Groq")


async def test_provider_status_tells_a_retired_model_and_its_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = await _groq_status_offering(monkeypatch, [settings.GROQ_FALLBACK_MODEL])
    assert (groq.configured, groq.available, groq.model) == (True, True, settings.GROQ_MODEL)
    assert f"retiré par Groq, secours {settings.GROQ_FALLBACK_MODEL}" in (groq.detail or "")


async def test_provider_status_is_down_when_no_model_is_left(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = await _groq_status_offering(monkeypatch, ["llama-3.1-8b-instant"])
    assert (groq.available, groq.detail) == (False, f"{settings.GROQ_MODEL} retiré par Groq")


@pytest.mark.usefixtures("no_llm")
async def test_system_status_lists_the_ai_providers(client: AsyncClient, admin_user: User) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    status = (await client.get("/api/v1/system/status", headers=headers)).json()
    names = [provider["name"] for provider in status["ai_providers"]]
    assert names == ["Groq", "Gemini", "Anthropic", "Ollama"]
