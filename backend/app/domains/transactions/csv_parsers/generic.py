import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.domains.transactions.csv_parsers.base import BaseCSVParser, ParsedTransaction

logger = logging.getLogger(__name__)

DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
)


def _date(value: str) -> datetime:
    if not value:
        return datetime.now()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.warning("Unrecognized date format: '%s', using current date", value)
    return datetime.now()


class GenericCSVParser(BaseCSVParser):
    """Format InvestAI : symbole, type, quantité et prix, en anglais ou en français."""

    name: ClassVar[str] = "InvestAI / Generic"
    supported_headers: ClassVar[tuple[str, ...]] = ("symbol", "type", "quantity", "price")
    TYPE_MAPPING: ClassVar[dict[str, str]] = {
        "buy": "buy",
        "achat": "buy",
        "sell": "sell",
        "vente": "sell",
        "transfer_in": "transfer_in",
        "transfert_entrant": "transfer_in",
        "deposit": "transfer_in",
        "transfer_out": "transfer_out",
        "transfert_sortant": "transfer_out",
        "withdrawal": "transfer_out",
        "dividend": "dividend",
        "dividende": "dividend",
        "staking_reward": "staking_reward",
        "staking": "staking",
        "unstaking": "unstaking",
        "airdrop": "airdrop",
        "conversion_in": "conversion_in",
        "conversion_out": "conversion_out",
    }

    def parse_row(self, row: dict[str, str]) -> list[ParsedTransaction]:
        """Ligne sans symbole ou sans type ignorée ; date absente ou illisible remplacée par maintenant."""
        symbol = row.get("symbol", "").strip().upper()
        trans_type = row.get("type", "").strip().lower()
        quantity_str = row.get("quantity", "0").strip()
        price_str = row.get("price", "0").strip()
        fee_str = row.get("fee", "0").strip()
        date_str = row.get("date", "").strip()
        notes = row.get("notes", "").strip()
        if not symbol or not trans_type:
            return []
        try:
            quantity = Decimal(quantity_str) if quantity_str else Decimal("0")
            price = Decimal(price_str) if price_str else Decimal("0")
            fee = Decimal(fee_str) if fee_str else Decimal("0")
        except InvalidOperation as e:
            raise ValueError(f"Invalid number: {e}") from e
        return [
            ParsedTransaction(
                symbol=symbol,
                transaction_type=self.TYPE_MAPPING.get(trans_type, trans_type),
                quantity=abs(quantity),
                price=price,
                fee=fee,
                currency="EUR",
                timestamp=_date(date_str),
                notes=notes or None,
            )
        ]
