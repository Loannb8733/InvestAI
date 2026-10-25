import pytest

from app.core.config import settings


@pytest.fixture
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun fournisseur configuré : l'Audit Lab retombe sur l'analyse statique."""
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_URL"):
        monkeypatch.setattr(settings, key, "")
