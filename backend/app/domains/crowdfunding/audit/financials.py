import logging
import re
from dataclasses import dataclass, field, fields

from app.domains.crowdfunding.audit.pdf_text import extract_tables, extract_text, find_number_near, parse_percent

logger = logging.getLogger(__name__)

LTV_LTC_PATTERN = re.compile(
    r"LTV\s*(?:\(.*?\))?\s*\|?\s*LTC\s*(?:\(.*?\))?\s*\n?\s*(\d[\d.,]*)\s*%\s*\|?\s*(\d[\d.,]*)\s*%",
    re.IGNORECASE,
)
REVENUE_KEYWORDS = ["chiffre d'affaires", "CA prévisionnel", "CA TTC", "prix de vente global"]
COST_KEYWORDS = ["prix de revient", "coût total", "coût de revient", "budget total", "coût global"]
RESALE_KEYWORDS = ["valeur vénale estimée", "valeur vénale après", "valeur après travaux"]
MARGIN_KEYWORDS = ["marge brute", "marge promoteur", "marge de sécurité", "marge opération"]
RATE_KEYWORDS = [
    "Taux annuel",
    "Rentabilité Cible",
    "rendement annuel",
    "taux de rendement",
    "TRI",
    "taux d'intérêt annuel",
]
DURATION_KEYWORDS = ["Durée", "Maturité", "durée", "maturité"]
RAISE_KEYWORDS = [
    "Montant cible",
    "montant de la collecte",
    "objectif de collecte",
    "montant recherché",
    "émission obligataire",
]
PRE_SALES_KEYWORDS = ["pré-commercialisation", "pré commercialisation", "réservation", "lots vendus"]
EQUITY_KEYWORDS = ["fonds propres", "apport promoteur", "equity", "skin in the game"]
BOUNDS = {"ltv": (0, 100), "ltc": (0, 150), "target_rate": (0, 50)}


@dataclass
class ExtractedFinancials:
    """Chiffres d'un dossier de crowdfunding lus dans le PDF."""

    revenue: float | None = None
    cost_price: float | None = None
    gross_margin: float | None = None
    gross_margin_percent: float | None = None
    target_rate: float | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    raise_amount: float | None = None
    ltv: float | None = None
    ltc: float | None = None
    pre_sales: float | None = None
    equity: float | None = None
    raw_tables: list[str] = field(default_factory=list)


MERGED_FIELDS = tuple(f.name for f in fields(ExtractedFinancials) if f.name != "raw_tables")


def _compute_margin(result: ExtractedFinancials) -> None:
    if result.revenue and result.cost_price:
        result.gross_margin = result.revenue - result.cost_price
        if result.revenue > 0:
            result.gross_margin_percent = round((result.gross_margin / result.revenue) * 100, 2)


def _margin(text: str, result: ExtractedFinancials) -> None:
    result.revenue = find_number_near(text, REVENUE_KEYWORDS)
    result.cost_price = find_number_near(text, COST_KEYWORDS)
    _compute_margin(result)
    if result.revenue is None:
        result.revenue = find_number_near(text, RESALE_KEYWORDS, window=300)
    _compute_margin(result)
    if result.gross_margin_percent is None:
        result.gross_margin_percent = find_number_near(text, MARGIN_KEYWORDS, is_percent=True)


def _duration(text: str, result: ExtractedFinancials) -> None:
    span = re.search(r"(\d+)\s*(?:à|[-–])\s*(\d+)\s*mois", text)  # noqa: RUF001
    if span:
        result.duration_min, result.duration_max = int(span.group(1)), int(span.group(2))
        return
    for keyword in DURATION_KEYWORDS:
        index = text.find(keyword)
        if index < 0:
            continue
        months = re.search(r"(\d{1,3})\s*mois", text[index : index + 100])
        if months:
            result.duration_min = result.duration_max = int(months.group(1))
            return


def _leverage(text: str, result: ExtractedFinancials) -> None:
    pair = LTV_LTC_PATTERN.search(text)
    if pair:
        result.ltv = parse_percent(pair.group(1) + "%")
        result.ltc = parse_percent(pair.group(2) + "%")
        return
    result.ltv = find_number_near(text, ["LTV", "Loan-to-Value", "loan to value"], is_percent=True)
    result.ltc = find_number_near(text, ["LTC", "Loan-to-Cost", "loan to cost"], is_percent=True)


def _discard_implausible(result: ExtractedFinancials) -> None:
    for name, (low, high) in BOUNDS.items():
        value = getattr(result, name)
        if value is not None and not (low < value <= high):
            logger.warning("PDF extraction: %s=%.1f%% out of bounds, discarding", name, value)
            setattr(result, name, None)
    if result.gross_margin_percent is not None and not (-50 < result.gross_margin_percent <= 80):
        logger.warning("PDF extraction: margin=%.1f%% out of bounds, discarding", result.gross_margin_percent)
        result.gross_margin_percent = None
    if result.pre_sales is not None and not (0 <= result.pre_sales <= 100):
        logger.warning("PDF extraction: pre-comm=%.1f%% out of bounds, discarding", result.pre_sales)
        result.pre_sales = None


def extract_financials(file_bytes: bytes) -> ExtractedFinancials:
    """Chiffre d'affaires, coût, marge, TRI, durée, collecte, LTV/LTC, pré-commercialisation et fonds propres du PDF.

    Les valeurs hors des bornes plausibles sont écartées.
    """
    text = extract_text(file_bytes)
    result = ExtractedFinancials(raw_tables=extract_tables(file_bytes))
    _margin(text, result)
    result.target_rate = find_number_near(text, RATE_KEYWORDS, is_percent=True)
    _duration(text, result)
    result.raise_amount = find_number_near(text, RAISE_KEYWORDS)
    _leverage(text, result)
    result.pre_sales = find_number_near(text, PRE_SALES_KEYWORDS, is_percent=True)
    result.equity = find_number_near(text, EQUITY_KEYWORDS)
    _discard_implausible(result)
    return result
