"""Base exchange service interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


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
    tx_id: Optional[str] = None


@dataclass
class ExchangeWithdrawal:
    """A withdrawal from an exchange."""

    withdrawal_id: str
    symbol: str
    amount: Decimal
    fee: Decimal
    timestamp: datetime
    status: str
    tx_id: Optional[str] = None
    address: Optional[str] = None


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

    def __init__(self, api_key: str, secret_key: str, passphrase: Optional[str] = None):
        """Initialize exchange service with credentials."""
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange name."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        pass

    @abstractmethod
    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from the exchange."""
        pass

    @abstractmethod
    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from the exchange."""
        pass

    @abstractmethod
    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from the exchange."""
        pass

    @abstractmethod
    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from the exchange."""
        pass

    async def get_fiat_orders(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List["ExchangeFiatOrder"]:
        """Get fiat buy/sell order history. Optional method - not all exchanges support this."""
        return []

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to standard format (e.g., BTC, ETH)."""
        # Remove common quote currencies
        for quote in ["USDT", "BUSD", "USD", "EUR", "BTC", "ETH"]:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return symbol[: -len(quote)]
        return symbol
