import csv
import io

from app.domains.transactions.csv_parsers.base import BaseCSVParser
from app.domains.transactions.csv_parsers.binance import BinanceCSVParser
from app.domains.transactions.csv_parsers.crypto_com import CryptoComCSVParser
from app.domains.transactions.csv_parsers.generic import GenericCSVParser
from app.domains.transactions.csv_parsers.kraken import KrakenCSVParser

AVAILABLE_PARSERS: tuple[type[BaseCSVParser], ...] = (
    CryptoComCSVParser,
    BinanceCSVParser,
    KrakenCSVParser,
    GenericCSVParser,
)


def _headers(content: str) -> list[str]:
    headers: list[str] = []
    for delimiter in (",", ";", "\t"):
        try:
            headers = next(csv.reader(io.StringIO(content), delimiter=delimiter), [])
            if headers and len(headers) > 1:
                break
        except Exception:  # noqa: BLE001
            continue
    return headers


def detect_csv_format(content: str) -> BaseCSVParser | None:
    """Premier lecteur, du plus spécifique au générique, dont les colonnes figurent dans l'en-tête."""
    headers = _headers(content)
    if not headers:
        return None
    for parser_class in AVAILABLE_PARSERS:
        if parser_class.can_parse(headers):
            return parser_class()
    return None


def get_parser_by_name(name: str) -> BaseCSVParser | None:
    """Lecteur dont le nom égale ou contient ``name``, sans tenir compte de la casse."""
    name_lower = name.lower()
    for parser_class in AVAILABLE_PARSERS:
        if parser_class.name.lower() == name_lower or name_lower in parser_class.name.lower():
            return parser_class()
    return None


def get_available_platforms() -> list[str]:
    """Noms des plateformes importables."""
    return [p.name for p in AVAILABLE_PARSERS]
