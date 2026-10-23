"""Base exchange service interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ExchangeBalance:
    """Balance for a single asset on an exchange."""

    symbol: str
    free: Decimal
    locked: Decimal
    total: Decimal


@dataclass
class ExchangeTrade:
    """A trade from an exchange."""

    trade_id: str
    symbol: str
    side: str  # buy or sell
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    timestamp: datetime


@dataclass
class ExchangeDeposit:
    """A deposit to an exchange."""

    deposit_id: str
    symbol: str
    amount: Decimal
    timestamp: datetime
    status: str
    tx_id: str | None = None


@dataclass
class ExchangeWithdrawal:
    """A withdrawal from an exchange."""

    withdrawal_id: str
    symbol: str
    amount: Decimal
    fee: Decimal
    timestamp: datetime
    status: str
    tx_id: str | None = None
    address: str | None = None


@dataclass
class ExchangeFiatOrder:
    """A fiat buy/sell order from an exchange."""

    order_id: str
    crypto_symbol: str
    fiat_currency: str
    side: str  # buy or sell
    crypto_amount: Decimal
    fiat_amount: Decimal
    price: Decimal  # fiat per crypto
    fee: Decimal
    status: str
    timestamp: datetime


class BaseExchangeService(ABC):
    """Abstract base class for exchange services."""

    def __init__(
        self,
        api_key: str,
        secret_key: str | None = None,
        passphrase: str | None = None,
    ):
        """Initialize exchange service with credentials."""
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange name."""

    def _require_secret_key(self) -> str:
        if self.secret_key is None:
            raise ValueError(f"{self.exchange_name} requires a secret key")
        return self.secret_key

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the API connection is working."""

    async def connection_error(self) -> str | None:
        """Motif lisible d'un échec de connexion, quand l'exchange le donne."""
        return None

    @abstractmethod
    async def get_balances(self) -> list[ExchangeBalance]:
        """Get all non-zero balances from the exchange."""

    @abstractmethod
    async def get_trades(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Get trade history from the exchange."""

    @abstractmethod
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        """Get deposit history from the exchange."""

    @abstractmethod
    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        """Get withdrawal history from the exchange."""

    async def get_fiat_orders(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list["ExchangeFiatOrder"]:
        """Get fiat buy/sell order history. Optional method - not all exchanges support this."""
        return []

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to standard format (e.g., BTC, ETH)."""
        # Remove common quote currencies
        for quote in ["USDT", "BUSD", "USD", "EUR", "BTC", "ETH"]:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return symbol[: -len(quote)]
        return symbol
