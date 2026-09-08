"""D'où vient une analyse de l'Audit Lab, et comment le lecteur le sait.

`analyze_documents` enchaîne quatre fournisseurs — Groq, Gemini, Anthropic,
Ollama — puis retombe sur `_analyze_statically`, une extraction par expressions
régulières, si tous échouent **ou si aucune clé n'est configurée**.

Le repli est légitime : mieux vaut des chiffres extraits d'un PDF que rien du
tout. Ce qui ne l'était pas, c'est qu'il soit **indistinguable** d'une vraie
analyse — mêmes scores, même radar, même verdict à l'écran. C'est le motif de
NEW-35 (alertes) et NEW-36 (diversification) : une valeur de secours que
l'appelant, et ici le lecteur, évaluent comme un résultat.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.project_audit import ProjectAudit
from app.services.ai.crowdfunding_analyzer import CrowdfundingAnalyzerService


@pytest.fixture
def analyseur():
    return CrowdfundingAnalyzerService()


@pytest.fixture
def pdf_minimal():
    """Un vrai PDF, pas des octets qui y ressemblent.

    Le service extrait le texte avant tout : un fichier factice le fait échouer
    sur une erreur de format, bien avant d'atteindre la cascade de fournisseurs
    que ces tests visent.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Projet test — TRI 9 % — collecte 500 000 EUR")
    octets = doc.tobytes()
    doc.close()
    return [("projet.pdf", octets)]


def _sans_fournisseur(monkeypatch):
    """Aucune clé configurée : la cascade est vide, le repli statique s'applique."""
    from app.core.config import settings

    for cle in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_URL"):
        monkeypatch.setattr(settings, cle, None, raising=False)


class TestProvenance:
    async def test_sans_fournisseur_l_audit_se_declare_statique(
        self, db_session, regular_user, analyseur, pdf_minimal, monkeypatch
    ):
        """Le champ `analysis_source` dit ce qui a produit les chiffres.

        Sans lui, rien ne séparait une analyse par modèle de langage d'une
        extraction par expressions régulières : le lecteur voyait le même
        radar dans les deux cas.
        """
        _sans_fournisseur(monkeypatch)

        audit = await analyseur.analyze_documents(db_session, pdf_minimal, regular_user.id, None)

        assert audit.analysis_source == "statique"

    async def test_un_fournisseur_qui_repond_est_nomme(
        self, db_session, regular_user, analyseur, pdf_minimal, monkeypatch
    ):
        from app.core.config import settings

        _sans_fournisseur(monkeypatch)
        monkeypatch.setattr(settings, "GROQ_API_KEY", "cle-de-test", raising=False)

        reponse = '{"project_name": "Résidence Test", "verdict": "GO", "risk_score": 72}'
        with patch.object(analyseur, "_call_groq", new=AsyncMock(return_value=reponse)):
            audit = await analyseur.analyze_documents(db_session, pdf_minimal, regular_user.id, None)

        assert audit.analysis_source == "Groq"
        assert audit.project_name == "Résidence Test"

    async def test_un_fournisseur_en_panne_passe_au_suivant_et_le_dit(
        self, db_session, regular_user, analyseur, pdf_minimal, monkeypatch
    ):
        """La cascade nomme celui qui a répondu, pas le premier tenté."""
        from app.core.config import settings

        _sans_fournisseur(monkeypatch)
        monkeypatch.setattr(settings, "GROQ_API_KEY", "cle-de-test", raising=False)
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "cle-de-test", raising=False)

        with patch.object(analyseur, "_call_groq", new=AsyncMock(side_effect=RuntimeError("429"))), patch.object(
            analyseur, "_call_gemini", new=AsyncMock(return_value='{"verdict": "VIGILANCE"}')
        ):
            audit = await analyseur.analyze_documents(db_session, pdf_minimal, regular_user.id, None)

        assert audit.analysis_source == "Gemini"

    async def test_une_reponse_illisible_retombe_sur_le_statique(
        self, db_session, regular_user, analyseur, pdf_minimal, monkeypatch
    ):
        """Un modèle qui ne rend pas de JSON exploitable ne vaut pas mieux qu'aucun.

        Le repli s'applique, et l'audit le dit — sans quoi le lecteur croirait
        lire l'avis d'un modèle alors qu'il lit des expressions régulières.
        """
        from app.core.config import settings

        _sans_fournisseur(monkeypatch)
        monkeypatch.setattr(settings, "GROQ_API_KEY", "cle-de-test", raising=False)

        with patch.object(analyseur, "_call_groq", new=AsyncMock(return_value="je ne sais pas répondre")):
            audit = await analyseur.analyze_documents(db_session, pdf_minimal, regular_user.id, None)

        assert audit.analysis_source == "statique"

    async def test_la_provenance_est_persistee(self, db_session, regular_user, analyseur, pdf_minimal, monkeypatch):
        # Relue depuis la base : l'écran la lira comme n'importe quel autre champ.
        _sans_fournisseur(monkeypatch)

        audit = await analyseur.analyze_documents(db_session, pdf_minimal, regular_user.id, None)
        await db_session.commit()

        relu = await db_session.get(ProjectAudit, audit.id)

        assert relu.analysis_source == "statique"
