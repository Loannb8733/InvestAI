"""CSV parsers for different exchange platforms."""

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple, Type


@dataclass
class ParsedTransaction:
    """Standardized transaction data from CSV."""

    symbol: str
    transaction_type: str  # buy, sell, transfer_in, transfer_out, conversion_out, conversion_in, staking_reward, etc.
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    timestamp: datetime
    notes: Optional[str] = None
    to_symbol: Optional[str] = None  # For conversions
    to_quantity: Optional[Decimal] = None  # For conversions


_TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
]


def parse_timestamp(value: str) -> datetime:
    """Parse a timestamp string trying multiple formats."""
    value = value.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid timestamp: {value}")


class BaseCSVParser(ABC):
    """Base class for CSV parsers."""

    name: str = "Generic"
    supported_headers: List[str] = []

    @classmethod
    def can_parse(cls, headers: List[str]) -> bool:
        """Check if this parser can handle the CSV based on headers."""
        headers_lower = [h.lower().strip() for h in headers]
        return all(h.lower() in headers_lower for h in cls.supported_headers)

    @abstractmethod
    def parse_row(self, row: dict) -> List[ParsedTransaction]:
        """Parse a single row and return list of transactions."""
        pass

    def parse_csv(self, content: str) -> Tuple[List[ParsedTransaction], List[str]]:
        """Parse entire CSV content and return transactions and errors."""
        transactions = []
        errors = []

        # Try different delimiters
        for delimiter in [',', ';', '\t']:
            try:
                reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
                if reader.fieldnames and len(reader.fieldnames) > 1:
                    break
            except Exception:
                continue

        if not reader.fieldnames:
            errors.append("Could not parse CSV headers")
            return transactions, errors

        # Normalize headers
        reader.fieldnames = [f.lower().strip() for f in reader.fieldnames]

        for row_num, row in enumerate(reader, start=2):
            try:
                parsed = self.parse_row(row)
                transactions.extend(parsed)
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return transactions, errors


class CryptoComCSVParser(BaseCSVParser):
    """Parser for Crypto.com CSV exports."""

    name = "Crypto.com"
    supported_headers = ["timestamp (utc)", "transaction description", "currency", "amount", "transaction kind"]

    # Map Crypto.com transaction kinds to our types
    KIND_MAPPING = {
        "crypto_exchange": "conversion",
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

    def parse_row(self, row: dict) -> List[ParsedTransaction]:
        """Parse a Crypto.com CSV row."""
        transactions = []

        # Get basic fields
        timestamp_str = row.get("timestamp (utc)", "").strip()
        description = row.get("transaction description", "").strip()
        currency = row.get("currency", "").strip()
        amount_str = row.get("amount", "0").strip()
        to_currency = row.get("to currency", "").strip()
        to_amount_str = row.get("to amount", "0").strip()
        native_currency = row.get("native currency", "EUR").strip()
        native_amount_str = row.get("native amount", "0").strip()
        kind = row.get("transaction kind", "").strip().lower()

        # Parse timestamp
        timestamp = parse_timestamp(timestamp_str)

        # Parse amounts
        try:
            amount = Decimal(amount_str) if amount_str else Decimal("0")
            to_amount = Decimal(to_amount_str) if to_amount_str else Decimal("0")
            native_amount = Decimal(native_amount_str) if native_amount_str else Decimal("0")
        except InvalidOperation as e:
            raise ValueError(f"Invalid amount: {e}")

        # Determine transaction type
        trans_type = self.KIND_MAPPING.get(kind, "unknown")

        if trans_type == "unknown":
            # Skip unknown transaction types
            return transactions

        # Handle conversions (crypto_exchange)
        if kind == "crypto_exchange" and to_currency:
            # This is a crypto-to-crypto conversion
            # Create CONVERSION_OUT for the source
            if amount < 0:
                price = abs(native_amount / amount) if amount != 0 else Decimal("0")
                transactions.append(ParsedTransaction(
                    symbol=currency,
                    transaction_type="conversion_out",
                    quantity=abs(amount),
                    price=price,
                    fee=Decimal("0"),
                    currency=native_currency,
                    timestamp=timestamp,
                    notes=f"Crypto.com: {description}",
                    to_symbol=to_currency,
                    to_quantity=to_amount,
                ))

                # Create CONVERSION_IN for the destination
                to_price = abs(native_amount / to_amount) if to_amount != 0 else Decimal("0")
                transactions.append(ParsedTransaction(
                    symbol=to_currency,
                    transaction_type="conversion_in",
                    quantity=to_amount,
                    price=to_price,
                    fee=Decimal("0"),
                    currency=native_currency,
                    timestamp=timestamp,
                    notes=f"Crypto.com: {description}",
                ))

        # Handle purchases (viban_purchase, google_pay, etc.)
        elif trans_type == "buy" and to_currency and to_amount > 0:
            price = abs(native_amount / to_amount) if to_amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=to_currency,
                transaction_type="buy",
                quantity=to_amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle direct crypto purchases (google_pay, apple_pay format where crypto is in Currency field)
        elif trans_type == "buy" and not to_currency and amount > 0 and currency not in ["EUR", "USD", "GBP"]:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="buy",
                quantity=amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle sells (crypto_viban_exchange)
        elif trans_type == "sell" and amount < 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="sell",
                quantity=abs(amount),
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle deposits
        elif trans_type == "transfer_in" and amount > 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="transfer_in",
                quantity=amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle withdrawals
        elif trans_type == "transfer_out" and amount < 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="transfer_out",
                quantity=abs(amount),
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle staking rewards
        elif trans_type == "staking_reward" and amount > 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="staking_reward",
                quantity=amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle airdrops
        elif trans_type == "airdrop" and amount > 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="airdrop",
                quantity=amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: {description}",
            ))

        # Handle balance conversions (swap credited/debited)
        elif kind == "crypto_wallet_swap_debited" and amount < 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="conversion_out",
                quantity=abs(amount),
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: Balance Conversion",
            ))

        elif kind == "crypto_wallet_swap_credited" and amount > 0:
            price = abs(native_amount / amount) if amount != 0 else Decimal("0")
            transactions.append(ParsedTransaction(
                symbol=currency,
                transaction_type="conversion_in",
                quantity=amount,
                price=price,
                fee=Decimal("0"),
                currency=native_currency,
                timestamp=timestamp,
                notes=f"Crypto.com: Balance Conversion",
            ))

        return transactions


class BinanceCSVParser(BaseCSVParser):
    """Parser for Binance CSV exports."""

    name = "Binance"
    supported_headers = ["utc_time", "operation", "coin", "change"]

    OPERATION_MAPPING = {
        "buy": "buy",
        "sell": "sell",
        "deposit": "transfer_in",
        "withdraw": "transfer_out",
        "commission": "fee",
        "staking rewards": "staking_reward",
        "eth 2.0 staking rewards": "staking_reward",
        "simple earn flexible interest": "staking_reward",
        "simple earn locked rewards": "staking_reward",
        "distribution": "airdrop",
        "airdrop": "airdrop",
        "small assets exchange bnb": "conversion",
        "convert": "conversion",
    }

    def parse_row(self, row: dict) -> List[ParsedTransaction]:
        """Parse a Binance CSV row."""
        transactions = []

        timestamp_str = row.get("utc_time", "").strip()
        operation = row.get("operation", "").strip().lower()
        coin = row.get("coin", "").strip()
        change_str = row.get("change", "0").strip()

        # Parse timestamp
        timestamp = parse_timestamp(timestamp_str)

        # Parse amount
        try:
            change = Decimal(change_str) if change_str else Decimal("0")
        except InvalidOperation:
            raise ValueError(f"Invalid change amount: {change_str}")

        trans_type = self.OPERATION_MAPPING.get(operation, "unknown")

        if trans_type == "unknown" or change == 0:
            return transactions

        if trans_type == "conversion":
            # Binance conversion - negative is out, positive is in
            if change < 0:
                trans_type = "conversion_out"
            else:
                trans_type = "conversion_in"

        transactions.append(ParsedTransaction(
            symbol=coin,
            transaction_type=trans_type,
            quantity=abs(change),
            price=Decimal("0"),  # Binance CSV doesn't include price
            fee=Decimal("0"),
            currency="EUR",
            timestamp=timestamp,
            notes=f"Binance: {operation}",
        ))

        return transactions


class KrakenCSVParser(BaseCSVParser):
    """Parser for Kraken CSV exports (ledgers)."""

    name = "Kraken"
    supported_headers = ["txid", "refid", "time", "type", "asset", "amount", "fee"]

    # Kraken asset name mapping
    ASSET_MAP = {
        "XXBT": "BTC",
        "XBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XLTC": "LTC",
        "ZUSD": "USD",
        "ZEUR": "EUR",
    }

    TYPE_MAPPING = {
        "deposit": "transfer_in",
        "withdrawal": "transfer_out",
        "trade": "trade",
        "staking": "staking_reward",
        "reward": "airdrop",  # Spin & Win, promotions
        "bonus": "airdrop",
        "earn": "staking_reward",
        "credit": "airdrop",
        "airdrop": "airdrop",
        "transfer": "transfer_in",
        "spend": "sell",
        "receive": "transfer_in",
    }

    def _normalize_asset(self, asset: str) -> str:
        """Normalize Kraken asset names."""
        if asset in self.ASSET_MAP:
            return self.ASSET_MAP[asset]
        if asset.startswith("X") and len(asset) == 4:
            return asset[1:]
        if asset.startswith("Z") and len(asset) == 4:
            return asset[1:]
        return asset

    def parse_row(self, row: dict) -> List[ParsedTransaction]:
        """Parse a Kraken CSV row."""
        transactions = []

        timestamp_str = row.get("time", "").strip()
        tx_type = row.get("type", "").strip().lower()
        asset = row.get("asset", "").strip()
        amount_str = row.get("amount", "0").strip()
        fee_str = row.get("fee", "0").strip()

        # Normalize asset name
        symbol = self._normalize_asset(asset)

        # Skip fiat currencies
        if symbol in ["EUR", "USD", "GBP", "CAD"]:
            return transactions

        # Parse timestamp
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                timestamp = datetime.strptime(timestamp_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise ValueError(f"Invalid timestamp: {timestamp_str}")

        # Parse amounts
        try:
            amount = Decimal(amount_str) if amount_str else Decimal("0")
            fee = Decimal(fee_str) if fee_str else Decimal("0")
        except InvalidOperation:
            raise ValueError(f"Invalid amount: {amount_str}")

        trans_type = self.TYPE_MAPPING.get(tx_type, "unknown")

        if trans_type == "unknown" or amount == 0:
            return transactions

        # For trades, determine buy/sell based on amount sign
        if trans_type == "trade":
            trans_type = "buy" if amount > 0 else "sell"

        transactions.append(ParsedTransaction(
            symbol=symbol,
            transaction_type=trans_type,
            quantity=abs(amount),
            price=Decimal("0"),  # Would need to calculate from paired fiat entry
            fee=abs(fee),
            currency="EUR",
            timestamp=timestamp,
            notes=f"Kraken: {tx_type}",
        ))

        return transactions


class GenericCSVParser(BaseCSVParser):
    """Generic CSV parser for InvestAI format."""

    name = "InvestAI / Generic"
    supported_headers = ["symbol", "type", "quantity", "price"]

    def parse_row(self, row: dict) -> List[ParsedTransaction]:
        """Parse a generic CSV row."""
        transactions = []

        symbol = row.get("symbol", "").strip().upper()
        trans_type = row.get("type", "").strip().lower()
        quantity_str = row.get("quantity", "0").strip()
        price_str = row.get("price", "0").strip()
        fee_str = row.get("fee", "0").strip()
        date_str = row.get("date", "").strip()
        notes = row.get("notes", "").strip()

        if not symbol or not trans_type:
            return transactions

        # Parse amounts
        try:
            quantity = Decimal(quantity_str) if quantity_str else Decimal("0")
            price = Decimal(price_str) if price_str else Decimal("0")
            fee = Decimal(fee_str) if fee_str else Decimal("0")
        except InvalidOperation as e:
            raise ValueError(f"Invalid number: {e}")

        # Parse date
        timestamp = datetime.now()
        if date_str:
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"]:
                try:
                    timestamp = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        # Map transaction types
        type_mapping = {
            "buy": "buy", "achat": "buy",
            "sell": "sell", "vente": "sell",
            "transfer_in": "transfer_in", "transfert_entrant": "transfer_in", "deposit": "transfer_in",
            "transfer_out": "transfer_out", "transfert_sortant": "transfer_out", "withdrawal": "transfer_out",
            "dividend": "dividend", "dividende": "dividend",
            "staking_reward": "staking_reward", "staking": "staking_reward",
            "airdrop": "airdrop",
            "conversion_in": "conversion_in",
            "conversion_out": "conversion_out",
        }

        mapped_type = type_mapping.get(trans_type, trans_type)

        transactions.append(ParsedTransaction(
            symbol=symbol,
            transaction_type=mapped_type,
            quantity=abs(quantity),
            price=price,
            fee=fee,
            currency="EUR",
            timestamp=timestamp,
            notes=notes or None,
        ))

        return transactions


# List of available parsers (order matters - more specific first)
AVAILABLE_PARSERS: List[Type[BaseCSVParser]] = [
    CryptoComCSVParser,
    BinanceCSVParser,
    KrakenCSVParser,
    GenericCSVParser,
]


def detect_csv_format(content: str) -> Optional[BaseCSVParser]:
    """Auto-detect the CSV format based on headers."""
    # Try different delimiters
    for delimiter in [',', ';', '\t']:
        try:
            reader = csv.reader(io.StringIO(content), delimiter=delimiter)
            headers = next(reader, [])
            if headers and len(headers) > 1:
                break
        except Exception:
            continue

    if not headers:
        return None

    # Try each parser
    for parser_class in AVAILABLE_PARSERS:
        if parser_class.can_parse(headers):
            return parser_class()

    return None


def get_parser_by_name(name: str) -> Optional[BaseCSVParser]:
    """Get a parser by platform name."""
    name_lower = name.lower()
    for parser_class in AVAILABLE_PARSERS:
        if parser_class.name.lower() == name_lower or name_lower in parser_class.name.lower():
            return parser_class()
    return None


def get_available_platforms() -> List[str]:
    """Get list of available platform names."""
    return [p.name for p in AVAILABLE_PARSERS]
