"""Structured PDF text extraction for crowdfunding documents."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFinancials:
    """Financial data extracted from PDF tables."""

    chiffre_affaires: Optional[float] = None
    prix_revient: Optional[float] = None
    marge_brute: Optional[float] = None
    marge_brute_percent: Optional[float] = None
    tri: Optional[float] = None
    duration_min: Optional[int] = None
    duration_max: Optional[int] = None
    collecte: Optional[float] = None
    ltv: Optional[float] = None
    ltc: Optional[float] = None
    pre_commercialisation: Optional[float] = None
    fonds_propres: Optional[float] = None
    raw_tables: list[str] = field(default_factory=list)


def _parse_euro(s: str) -> Optional[float]:
    """Parse a French-formatted euro amount like '3 456 789 €' or '3.456.789€'."""
    cleaned = re.sub(r"[€\s]", "", s)
    cleaned = cleaned.replace("\xa0", "")
    # Handle French number format: 3.456.789,12 → 3456789.12
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


def _parse_percent(s: str) -> Optional[float]:
    """Parse a percentage like '11,5%' or '21.46 %'."""
    cleaned = re.sub(r"[%\s]", "", s)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find_number_near(text: str, keywords: list[str], is_percent: bool = False, window: int = 200) -> Optional[float]:
    """Find a number near given keywords in text."""
    text_lower = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        idx = text_lower.find(kw_lower)
        if idx < 0:
            continue
        # Look in the chars after the keyword
        region = text[idx : idx + window]
        if is_percent:
            match = re.search(r"(\d[\d\s.,]*\d)\s*%", region)
            if not match:
                # Single digit percentage like "5%"
                match = re.search(r"(\d)\s*%", region)
            if match:
                return _parse_percent(match.group(1) + "%")
        else:
            match = re.search(r"(\d[\d\s.,]*\d)\s*€", region)
            if match:
                return _parse_euro(match.group(0))
            # Try plain number
            match = re.search(r"(\d[\d\s.,]+\d)", region)
            if match:
                return _parse_euro(match.group(1))
    return None


def _clean_text(text: str) -> str:
    """Normalize extracted PDF text for better parsing."""
    # Normalize euro symbols
    text = re.sub(r"\bEUR\b|euros?", "€", text, flags=re.IGNORECASE)
    # Normalize dashes
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    # Remove control characters (keep newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize non-breaking spaces
    text = text.replace("\xa0", " ")
    # Collapse multiple spaces into one (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ consecutive blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


class PDFParser:
    """Extracts structured financial data from crowdfunding PDFs."""

    def extract_text(self, file_bytes: bytes) -> str:
        """Extract full text from PDF with cleanup."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(_clean_text(text))
        doc.close()
        return "\n\n---PAGE---\n\n".join(pages)

    def extract_tables(self, file_bytes: bytes) -> list[str]:
        """Extract text blocks that look like tables (lines with numbers)."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        tables = []
        for page in doc:
            blocks = page.get_text("blocks")
            for block in blocks:
                text = block[4] if len(block) > 4 else ""
                if isinstance(text, str) and re.search(r"\d.*[€%]", text):
                    tables.append(text.strip())
        doc.close()
        return tables

    def extract_financials(self, file_bytes: bytes) -> ExtractedFinancials:
        """Extract structured financial data from PDF."""
        text = self.extract_text(file_bytes)
        tables = self.extract_tables(file_bytes)
        result = ExtractedFinancials(raw_tables=tables)

        # Chiffre d'affaires
        result.chiffre_affaires = _find_number_near(
            text,
            ["chiffre d'affaires", "CA prévisionnel", "CA TTC", "prix de vente global"],
        )

        # Prix de revient / coût total
        result.prix_revient = _find_number_near(
            text,
            ["prix de revient", "coût total", "coût de revient", "budget total", "coût global"],
        )

        # Compute margin if both available
        if result.chiffre_affaires and result.prix_revient:
            result.marge_brute = result.chiffre_affaires - result.prix_revient
            if result.chiffre_affaires > 0:
                result.marge_brute_percent = round((result.marge_brute / result.chiffre_affaires) * 100, 2)

        # Fallback for renovation/marchand de biens: CA = valeur vénale after work
        if result.chiffre_affaires is None:
            result.chiffre_affaires = _find_number_near(
                text,
                ["valeur vénale estimée", "valeur vénale après", "valeur après travaux"],
                window=300,
            )

        # Recompute margin after fallback
        if result.chiffre_affaires and result.prix_revient:
            result.marge_brute = result.chiffre_affaires - result.prix_revient
            if result.chiffre_affaires > 0:
                result.marge_brute_percent = round((result.marge_brute / result.chiffre_affaires) * 100, 2)

        # Direct margin extraction as fallback
        if result.marge_brute_percent is None:
            result.marge_brute_percent = _find_number_near(
                text,
                ["marge brute", "marge promoteur", "marge de sécurité", "marge opération"],
                is_percent=True,
            )

        # TRI — prefer explicit "Taux annuel", "Rentabilité Cible" before generic matches
        result.tri = _find_number_near(
            text,
            [
                "Taux annuel",
                "Rentabilité Cible",
                "rendement annuel",
                "taux de rendement",
                "TRI",
                "taux d'intérêt annuel",
            ],
            is_percent=True,
        )

        # Duration — look for "N mois" patterns near duration keywords
        # First try range: "18 à 36 mois" or "18-36 mois"
        dur_match = re.search(r"(\d+)\s*(?:à|[-–])\s*(\d+)\s*mois", text)
        if dur_match:
            result.duration_min = int(dur_match.group(1))
            result.duration_max = int(dur_match.group(2))
        else:
            # Look for "N mois" near keywords like Durée, Maturité
            for kw in ["Durée", "Maturité", "durée", "maturité"]:
                idx = text.find(kw)
                if idx >= 0:
                    region = text[idx : idx + 100]
                    m = re.search(r"(\d{1,3})\s*mois", region)
                    if m:
                        d = int(m.group(1))
                        result.duration_min = d
                        result.duration_max = d
                        break

        # Collecte / montant
        result.collecte = _find_number_near(
            text,
            [
                "Montant cible",
                "montant de la collecte",
                "objectif de collecte",
                "montant recherché",
                "émission obligataire",
            ],
        )

        # LTV / LTC — handle "LTV (Loan To Value) | LTC (Loan To Cost)\n35% |43%" format
        ltv_ltc_match = re.search(
            r"LTV\s*(?:\(.*?\))?\s*\|?\s*LTC\s*(?:\(.*?\))?\s*\n?\s*" r"(\d[\d.,]*)\s*%\s*\|?\s*(\d[\d.,]*)\s*%",
            text,
            re.IGNORECASE,
        )
        if ltv_ltc_match:
            result.ltv = _parse_percent(ltv_ltc_match.group(1) + "%")
            result.ltc = _parse_percent(ltv_ltc_match.group(2) + "%")
        else:
            result.ltv = _find_number_near(text, ["LTV", "Loan-to-Value", "loan to value"], is_percent=True)
            result.ltc = _find_number_near(text, ["LTC", "Loan-to-Cost", "loan to cost"], is_percent=True)

        # Pré-commercialisation
        result.pre_commercialisation = _find_number_near(
            text,
            ["pré-commercialisation", "pré commercialisation", "réservation", "lots vendus"],
            is_percent=True,
        )

        # Fonds propres opérateur
        result.fonds_propres = _find_number_near(
            text,
            ["fonds propres", "apport promoteur", "equity", "skin in the game"],
        )

        logger.info(
            "PDF extraction: CA=%s, PR=%s, margin=%.2f%%, TRI=%s%%",
            result.chiffre_affaires,
            result.prix_revient,
            result.marge_brute_percent or 0,
            result.tri,
        )
        return result


pdf_parser = PDFParser()
