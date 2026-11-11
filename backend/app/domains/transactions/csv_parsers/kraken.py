from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.domains.transactions.csv_parsers.base import BaseCSVParser, ParsedTransaction, widest_reader

FIAT = frozenset({"EUR", "USD", "GBP", "CAD"})
KRAKEN_TIME = "%Y-%m-%d %H:%M:%S"
PAIRED_TYPES = frozenset({"trade", "spend", "receive"})

FiatLeg = tuple[str, Decimal]


def _timestamp(value: str) -> datetime:
    try:
        return datetime.strptime(value, KRAKEN_TIME)
    except ValueError:
        try:
            return datetime.strptime(value.split(".")[0], KRAKEN_TIME)
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {value}") from e


class KrakenCSVParser(BaseCSVParser):
    """Export des ledgers Kraken ; les lignes en monnaie fiat sont ignorées mais donnent le prix de leur échange."""

    name: ClassVar[str] = "Kraken"
    supported_headers: ClassVar[tuple[str, ...]] = ("txid", "refid", "time", "type", "asset", "amount", "fee")
    ASSET_MAP: ClassVar[dict[str, str]] = {
        "XXBT": "BTC",
        "XBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XLTC": "LTC",
        "XXDG": "DOGE",
        "XDG": "DOGE",
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

    def __init__(self) -> None:
        self._fiat_legs: dict[str, FiatLeg] = {}

    def _normalize_asset(self, asset: str) -> str:
        if asset in self.ASSET_MAP:
            return self.ASSET_MAP[asset]
        if asset.startswith(("X", "Z")) and len(asset) == 4:
            return asset[1:]
        return asset

    def _legs_by_refid(self, content: str) -> dict[str, FiatLeg]:
        reader = widest_reader(content)
        if reader is None or not reader.fieldnames:
            return {}
        reader.fieldnames = [f.lower().strip() for f in reader.fieldnames]
        legs: dict[str, list[FiatLeg]] = defaultdict(list)
        for row in reader:
            if (row.get("type") or "").strip().lower() not in PAIRED_TYPES:
                continue
            try:
                amount = Decimal((row.get("amount") or "").strip())
            except InvalidOperation:
                continue
            legs[(row.get("refid") or "").strip()].append(
                (self._normalize_asset((row.get("asset") or "").strip()), amount)
            )
        paired: dict[str, FiatLeg] = {}
        for refid, group in legs.items():
            fiat = [leg for leg in group if leg[0] in FIAT]
            if refid and len(group) == 2 and len(fiat) == 1:
                paired[refid] = fiat[0]
        return paired

    def parse_csv(self, content: str) -> tuple[list[ParsedTransaction], list[str]]:
        """Un échange crypto contre fiat (trade, ou spend et receive) prend son prix dans sa jambe fiat."""
        self._fiat_legs = self._legs_by_refid(content)
        return super().parse_csv(content)

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
        leg = self._fiat_legs.get(row.get("refid", "").strip()) if tx_type in PAIRED_TYPES else None
        if trans_type == "trade" or leg is not None:
            trans_type = "buy" if amount > 0 else "sell"
        return [
            ParsedTransaction(
                symbol=symbol,
                transaction_type=trans_type,
                quantity=abs(amount),
                price=abs(leg[1] / amount) if leg is not None else Decimal("0"),
                fee=abs(fee),
                currency=leg[0] if leg is not None else "EUR",
                timestamp=timestamp,
                notes=f"Kraken: {tx_type}",
            )
        ]
