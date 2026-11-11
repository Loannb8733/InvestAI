from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.domains.transactions.csv_parsers.base import BaseCSVParser, ParsedTransaction

FIAT = frozenset({"EUR", "USD", "GBP", "CAD"})
KRAKEN_TIME = "%Y-%m-%d %H:%M:%S"


def _timestamp(value: str) -> datetime:
    try:
        return datetime.strptime(value, KRAKEN_TIME)
    except ValueError:
        try:
            return datetime.strptime(value.split(".")[0], KRAKEN_TIME)
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {value}") from e


class KrakenCSVParser(BaseCSVParser):
    """Export des ledgers Kraken ; les lignes en monnaie fiat sont ignorées."""

    name: ClassVar[str] = "Kraken"
    supported_headers: ClassVar[tuple[str, ...]] = ("txid", "refid", "time", "type", "asset", "amount", "fee")
    ASSET_MAP: ClassVar[dict[str, str]] = {
        "XXBT": "BTC",
        "XBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XLTC": "LTC",
        "ZUSD": "USD",
        "ZEUR": "EUR",
    }
    TYPE_MAPPING: ClassVar[dict[str, str]] = {
        "deposit": "transfer_in",
        "withdrawal": "transfer_out",
        "trade": "trade",
        "staking": "staking_reward",
        "reward": "airdrop",
        "bonus": "airdrop",
        "earn": "staking_reward",
        "credit": "airdrop",
        "airdrop": "airdrop",
        "transfer": "transfer_in",
        "spend": "sell",
        "receive": "transfer_in",
    }

    def _normalize_asset(self, asset: str) -> str:
        if asset in self.ASSET_MAP:
            return self.ASSET_MAP[asset]
        if asset.startswith(("X", "Z")) and len(asset) == 4:
            return asset[1:]
        return asset

    def parse_row(self, row: dict[str, str]) -> list[ParsedTransaction]:
        """Un trade positif est un achat, négatif une vente ; type inconnu ou montant nul ignorés."""
        timestamp_str = row.get("time", "").strip()
        tx_type = row.get("type", "").strip().lower()
        asset = row.get("asset", "").strip()
        amount_str = row.get("amount", "0").strip()
        fee_str = row.get("fee", "0").strip()
        symbol = self._normalize_asset(asset)
        if symbol in FIAT:
            return []
        timestamp = _timestamp(timestamp_str)
        try:
            amount = Decimal(amount_str) if amount_str else Decimal("0")
            fee = Decimal(fee_str) if fee_str else Decimal("0")
        except InvalidOperation as e:
            raise ValueError(f"Invalid amount: {amount_str}") from e
        trans_type = self.TYPE_MAPPING.get(tx_type, "unknown")
        if trans_type == "unknown" or amount == 0:
            return []
        if trans_type == "trade":
            trans_type = "buy" if amount > 0 else "sell"
        return [
            ParsedTransaction(
                symbol=symbol,
                transaction_type=trans_type,
                quantity=abs(amount),
                price=Decimal("0"),
                fee=abs(fee),
                currency="EUR",
                timestamp=timestamp,
                notes=f"Kraken: {tx_type}",
            )
        ]
