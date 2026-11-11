from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.domains.transactions.csv_parsers.base import BaseCSVParser, ParsedTransaction, parse_timestamp

ZERO = Decimal("0")
EXCHANGE = "crypto_exchange"
SWAP_KINDS = frozenset({"crypto_wallet_swap_debited", "crypto_wallet_swap_credited"})
BALANCE_NOTE = "Crypto.com: Balance Conversion"
FIAT_PURCHASE_CURRENCIES = frozenset({"EUR", "USD", "GBP"})
OUTGOING = frozenset({"sell", "transfer_out", "conversion_out"})
INCOMING = frozenset({"transfer_in", "staking_reward", "airdrop", "conversion_in"})


def _decimal(value: str) -> Decimal:
    return Decimal(value) if value else ZERO


@dataclass(frozen=True)
class _Row:
    kind: str
    timestamp: datetime
    description: str
    currency: str
    amount: Decimal
    to_currency: str
    to_amount: Decimal
    native_currency: str
    native_amount: Decimal

    @classmethod
    def read(cls, row: dict[str, str]) -> "_Row":
        timestamp_str = row.get("timestamp (utc)", "").strip()
        description = row.get("transaction description", "").strip()
        currency = row.get("currency", "").strip()
        amount_str = row.get("amount", "0").strip()
        to_currency = row.get("to currency", "").strip()
        to_amount_str = row.get("to amount", "0").strip()
        native_currency = row.get("native currency", "EUR").strip()
        native_amount_str = row.get("native amount", "0").strip()
        kind = row.get("transaction kind", "").strip().lower()
        timestamp = parse_timestamp(timestamp_str)
        try:
            amount = _decimal(amount_str)
            to_amount = _decimal(to_amount_str)
            native_amount = _decimal(native_amount_str)
        except InvalidOperation as e:
            raise ValueError(f"Invalid amount: {e}") from e
        return cls(
            kind=kind,
            timestamp=timestamp,
            description=description,
            currency=currency,
            amount=amount,
            to_currency=to_currency,
            to_amount=to_amount,
            native_currency=native_currency,
            native_amount=native_amount,
        )

    def transaction(
        self,
        symbol: str,
        kind: str,
        quantity: Decimal,
        divisor: Decimal,
        to_symbol: str | None = None,
        to_quantity: Decimal | None = None,
    ) -> ParsedTransaction:
        return ParsedTransaction(
            symbol=symbol,
            transaction_type=kind,
            quantity=quantity,
            price=abs(self.native_amount / divisor) if divisor != 0 else ZERO,
            fee=ZERO,
            currency=self.native_currency,
            timestamp=self.timestamp,
            notes=BALANCE_NOTE if self.kind in SWAP_KINDS else f"Crypto.com: {self.description}",
            to_symbol=to_symbol,
            to_quantity=to_quantity,
        )


def _exchange(row: _Row) -> list[ParsedTransaction]:
    if row.amount > 0:
        return [row.transaction(row.currency, "conversion_in", row.amount, row.amount)]
    if not row.to_currency or row.amount == 0:
        return []
    sent = row.transaction(
        row.currency,
        "conversion_out",
        abs(row.amount),
        row.amount,
        to_symbol=row.to_currency,
        to_quantity=row.to_amount,
    )
    return [sent, row.transaction(row.to_currency, "conversion_in", row.to_amount, row.to_amount)]


def _purchase(row: _Row) -> list[ParsedTransaction]:
    if row.to_currency and row.to_amount > 0:
        return [row.transaction(row.to_currency, "buy", row.to_amount, row.to_amount)]
    if not row.to_currency and row.amount > 0 and row.currency not in FIAT_PURCHASE_CURRENCIES:
        return [row.transaction(row.currency, "buy", row.amount, row.amount)]
    return []


def _movement(row: _Row, kind: str) -> list[ParsedTransaction]:
    if (kind in OUTGOING and row.amount < 0) or (kind in INCOMING and row.amount > 0):
        return [row.transaction(row.currency, kind, abs(row.amount), row.amount)]
    return []


class CryptoComCSVParser(BaseCSVParser):
    """Export de l'application Crypto.com ; les types de transaction inconnus sont ignorés."""

    name: ClassVar[str] = "Crypto.com"
    supported_headers: ClassVar[tuple[str, ...]] = (
        "timestamp (utc)",
        "transaction description",
        "currency",
        "amount",
        "transaction kind",
    )
    KIND_MAPPING: ClassVar[dict[str, str]] = {
        EXCHANGE: "conversion",
        "viban_purchase": "buy",
        "crypto_deposit": "transfer_in",
        "crypto_withdrawal": "transfer_out",
        "crypto_viban_exchange": "sell",
        "crypto_wallet_swap_credited": "conversion_in",
        "crypto_wallet_swap_debited": "conversion_out",
        "trading.crypto_purchase.google_pay": "buy",
        "trading.crypto_purchase.apple_pay": "buy",
        "trading.crypto_purchase.card": "buy",
        "referral_bonus": "airdrop",
        "rewards_platform_deposit_credited": "staking_reward",
        "crypto_earn_interest_paid": "staking_reward",
        "staking_reward": "staking_reward",
        "supercharger_reward_to_app_credited": "staking_reward",
    }

    def parse_row(self, row: dict[str, str]) -> list[ParsedTransaction]:
        """Une conversion donne une sortie et une entrée quand la contrepartie est connue."""
        parsed = _Row.read(row)
        kind = self.KIND_MAPPING.get(parsed.kind)
        if kind is None:
            return []
        if parsed.kind == EXCHANGE:
            return _exchange(parsed)
        if kind == "buy":
            return _purchase(parsed)
        return _movement(parsed, kind)
