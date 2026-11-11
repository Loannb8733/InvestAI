from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.domains.transactions.csv_parsers.base import BaseCSVParser, ParsedTransaction, parse_timestamp


class BinanceCSVParser(BaseCSVParser):
    """Historique de transactions Binance : une ligne par mouvement signé, sans prix."""

    name: ClassVar[str] = "Binance"
    supported_headers: ClassVar[tuple[str, ...]] = ("utc_time", "operation", "coin", "change")
    OPERATION_MAPPING: ClassVar[dict[str, str]] = {
        "buy": "buy",
        "sell": "sell",
        "deposit": "transfer_in",
        "withdraw": "transfer_out",
        "commission": "fee",
        "staking rewards": "staking_reward",
        "eth 2.0 staking rewards": "staking_reward",
        "simple earn flexible interest": "staking_reward",
        "simple earn locked rewards": "staking_reward",
        "simple earn flexible subscription": "staking",
        "simple earn locked subscription": "staking",
        "simple earn flexible redemption": "unstaking",
        "simple earn locked redemption": "unstaking",
        "distribution": "airdrop",
        "airdrop": "airdrop",
        "small assets exchange bnb": "conversion",
        "convert": "conversion",
    }

    def parse_row(self, row: dict[str, str]) -> list[ParsedTransaction]:
        """Une conversion négative sort, positive entre ; opération inconnue ou montant nul ignorés."""
        timestamp_str = row.get("utc_time", "").strip()
        operation = row.get("operation", "").strip().lower()
        coin = row.get("coin", "").strip()
        change_str = row.get("change", "0").strip()
        timestamp = parse_timestamp(timestamp_str)
        try:
            change = Decimal(change_str) if change_str else Decimal("0")
        except InvalidOperation as e:
            raise ValueError(f"Invalid change amount: {change_str}") from e
        trans_type = self.OPERATION_MAPPING.get(operation, "unknown")
        if trans_type == "unknown" or change == 0:
            return []
        if trans_type == "conversion":
            trans_type = "conversion_out" if change < 0 else "conversion_in"
        return [
            ParsedTransaction(
                symbol=coin,
                transaction_type=trans_type,
                quantity=abs(change),
                price=Decimal("0"),
                fee=Decimal("0"),
                currency="EUR",
                timestamp=timestamp,
                notes=f"Binance: {operation}",
            )
        ]
