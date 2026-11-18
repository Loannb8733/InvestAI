import unicodedata

from app.domains.crowdfunding.audit.pdf_text import PAGE_SEPARATOR

PROMPT_BUDGET_CHARS = 14_000
KEYWORDS = (
    "tri ",
    "taux d'interet",
    "rendement",
    "ltv",
    "ltc",
    "marge",
    "garantie",
    "hypothe",
    "caution",
    "fiducie",
    "nantissement",
    "fonds propres",
    "apport",
    "collecte",
    "duree",
    "mois",
    "permis",
    "purge",
    "commercialisation",
    "reserv",
    "chiffre d'affaires",
    "porteur",
    "operateur",
    "emetteur",
    "prix de revient",
)

__all__ = ["PAGE_SEPARATOR", "PROMPT_BUDGET_CHARS", "select_pages"]


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _relevance(page: str) -> int:
    plain = _plain(page)
    return sum(keyword in plain for keyword in KEYWORDS)


def select_pages(texts: list[str], budget: int = PROMPT_BUDGET_CHARS) -> list[str]:
    """Pages utiles des documents, dans leur ordre d'origine, dans la limite de ``budget`` caractères.

    Le palier gratuit de Groq plafonne une requête à 8 000 tokens, réponse comprise : un dossier plus long est
    réduit aux pages qui contiennent le plus de mots-clés *différents* (TRI, garanties, permis…), sans tenir compte
    des accents. Compter les occurrences favorisait les pages d'étude de marché, où « taux » revient sans cesse.
    """
    if sum(len(text) for text in texts) <= budget:
        return texts
    pages = [page for text in texts for page in text.split(PAGE_SEPARATOR)]
    ranked = sorted(range(len(pages)), key=lambda index: (-_relevance(pages[index]), len(pages[index])))
    kept: set[int] = set()
    used = 0
    for index in ranked:
        if used + len(pages[index]) <= budget:
            kept.add(index)
            used += len(pages[index])
    return [PAGE_SEPARATOR.join(pages[index] for index in sorted(kept))]
