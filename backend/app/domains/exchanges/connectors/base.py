from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ExchangeBalance:
    """Solde d'un actif sur un exchange."""

    symbol: str
    free: Decimal
    locked: Decimal
    total: Decimal


@dataclass
class ExchangeTrade:
    """Exécution d'un ordre ; side vaut « buy » ou « sell »."""

    trade_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    timestamp: datetime


@dataclass
class ExchangeDeposit:
    """Dépôt reçu par l'exchange."""

    deposit_id: str
    symbol: str
    amount: Decimal
    timestamp: datetime
    status: str
    tx_id: str | None = None


@dataclass
class ExchangeWithdrawal:
    """Retrait sorti de l'exchange."""

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
    """Achat ou vente contre une devise ; price est en devise par unité de crypto."""

    order_id: str
    crypto_symbol: str
    fiat_currency: str
    side: str
    crypto_amount: Decimal
    fiat_amount: Decimal
    price: Decimal
    fee: Decimal
    status: str
    timestamp: datetime


class BaseExchangeService(ABC):
    """Connecteur d'un exchange : identifiants, soldes et historique."""

    def __init__(self, api_key: str, secret_key: str | None = None, passphrase: str | None = None) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Nom de l'exchange tel qu'il est enregistré sur les actifs."""

    def _require_secret_key(self) -> str:
        if self.secret_key is None:
            raise ValueError(f"{self.exchange_name} requires a secret key")
        return self.secret_key

    @abstractmethod
    async def test_connection(self) -> bool:
        """Vrai si l'exchange accepte les identifiants."""

    async def connection_error(self) -> str | None:
        """Motif lisible d'un échec de connexion, quand l'exchange le donne."""
        return None

    @abstractmethod
    async def get_balances(self) -> list[ExchangeBalance]:
        """Soldes non nuls."""

    @abstractmethod
    async def get_trades(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Historique des trades."""

    @abstractmethod
    async def get_deposits(
        self, symbol: str | None = None, start_time: datetime | None = None, limit: int = 100
    ) -> list[ExchangeDeposit]:
        """Historique des dépôts."""

    @abstractmethod
    async def get_withdrawals(
        self, symbol: str | None = None, start_time: datetime | None = None, limit: int = 100
    ) -> list[ExchangeWithdrawal]:
        """Historique des retraits."""

    async def get_fiat_orders(
        self, start_time: datetime | None = None, end_time: datetime | None = None, limit: int = 500
    ) -> list[ExchangeFiatOrder]:
        """Achats et ventes contre une devise ; vide pour un exchange qui ne les expose pas."""
        return []
