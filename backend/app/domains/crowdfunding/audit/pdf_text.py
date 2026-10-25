import re
from typing import Any

import pymupdf

PAGE_SEPARATOR = "\n\n---PAGE---\n\n"


def _open(file_bytes: bytes) -> Any:
    return pymupdf.open(stream=file_bytes, filetype="pdf")  # type: ignore[no-untyped-call]


def parse_euro(text: str) -> float | None:
    """Montant au format français (« 3 456 789 € », « 3.456.789,12 € »)."""
    cleaned = re.sub(r"[€\s]", "", text).replace("\xa0", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_percent(text: str) -> float | None:
    """Pourcentage (« 11,5% », « 21.46 % »)."""
    cleaned = re.sub(r"[%\s]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _number_in(region: str, is_percent: bool) -> tuple[bool, float | None]:
    if is_percent:
        match = re.search(r"(\d[\d\s.,]*\d)\s*%", region) or re.search(r"(\d)\s*%", region)
        return (True, parse_percent(match.group(1) + "%")) if match else (False, None)
    match = re.search(r"(\d[\d\s.,]*\d)\s*€", region)
    if match:
        return True, parse_euro(match.group(0))
    match = re.search(r"(\d[\d\s.,]+\d)", region)
    return (True, parse_euro(match.group(1))) if match else (False, None)


def find_number_near(text: str, keywords: list[str], is_percent: bool = False, window: int = 200) -> float | None:
    """Nombre (montant ou pourcentage) dans les ``window`` caractères du premier mot-clé suivi d'un nombre."""
    lowered = text.lower()
    for keyword in keywords:
        index = lowered.find(keyword.lower())
        if index < 0:
            continue
        found, value = _number_in(text[index : index + window], is_percent)
        if found:
            return value
    return None


def clean_text(text: str) -> str:
    """Texte normalisé : symbole €, tirets, espaces, caractères de contrôle et lignes vides."""
    text = re.sub(r"\bEUR\b|euros?", "€", text, flags=re.IGNORECASE)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def extract_text(file_bytes: bytes) -> str:
    """Texte nettoyé des pages non vides du PDF."""
    doc = _open(file_bytes)
    pages = [clean_text(text) for text in (page.get_text() for page in doc) if text.strip()]
    doc.close()
    return PAGE_SEPARATOR.join(pages)


def extract_tables(file_bytes: bytes) -> list[str]:
    """Blocs de texte qui contiennent un chiffre suivi d'un € ou d'un %."""
    doc = _open(file_bytes)
    tables = []
    for page in doc:
        for block in page.get_text("blocks"):
            text = block[4] if len(block) > 4 else ""
            if isinstance(text, str) and re.search(r"\d.*[€%]", text):
                tables.append(text.strip())
    doc.close()
    return tables
