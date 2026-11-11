import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import ClassVar

_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
)
_DELIMITERS = (";", ",", "\t")


@dataclass
class ParsedTransaction:
    """Transaction lue dans un export, au format commun à toutes les plateformes."""

    symbol: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    timestamp: datetime
    notes: str | None = None
    to_symbol: str | None = None
    to_quantity: Decimal | None = None


def parse_timestamp(value: str) -> datetime:
    """Horodatage dans le premier format reconnu ; ValueError sinon."""
    value = value.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid timestamp: {value}")


def _widest_reader(content: str) -> csv.DictReader[str] | None:
    reader = None
    best_col_count = 0
    for delimiter in _DELIMITERS:
        try:
            candidate = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            if candidate.fieldnames and len(candidate.fieldnames) > best_col_count:
                best_col_count = len(candidate.fieldnames)
                reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        except Exception:  # noqa: BLE001
            continue
    return reader


class BaseCSVParser(ABC):
    """Lecteur d'un export CSV : en-têtes reconnus et conversion ligne à ligne."""

    name: ClassVar[str] = "Generic"
    supported_headers: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def can_parse(cls, headers: list[str]) -> bool:
        """Vrai si toutes les colonnes attendues figurent parmi ``headers``, sans tenir compte de la casse."""
        headers_lower = [h.lower().strip() for h in headers]
        return all(h.lower() in headers_lower for h in cls.supported_headers)

    @abstractmethod
    def parse_row(self, row: dict[str, str]) -> list[ParsedTransaction]:
        """Transactions d'une ligne, aux en-têtes en minuscules."""

    def parse_csv(self, content: str) -> tuple[list[ParsedTransaction], list[str]]:
        """Transactions du fichier et erreurs par ligne, avec le séparateur qui donne le plus de colonnes."""
        transactions: list[ParsedTransaction] = []
        errors: list[str] = []
        reader = _widest_reader(content)
        if reader is None or not reader.fieldnames:
            errors.append("Could not parse CSV headers")
            return transactions, errors
        reader.fieldnames = [f.lower().strip() for f in reader.fieldnames]
        for row_num, row in enumerate(reader, start=2):
            try:
                transactions.extend(self.parse_row(row))
            except Exception as e:  # noqa: BLE001
                errors.append(f"Row {row_num}: {e!s}")
        return transactions, errors
