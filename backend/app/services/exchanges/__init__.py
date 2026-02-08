"""Exchange services package."""

from app.services.exchanges.base import BaseExchangeService
from app.services.exchanges.binance import BinanceService
from app.services.exchanges.kraken import KrakenService
from app.services.exchanges.cryptocom import CryptoComService

EXCHANGE_SERVICES = {
    "binance": BinanceService,
    "kraken": KrakenService,
}

SUPPORTED_EXCHANGES = [
    {
        "id": "binance",
        "name": "Binance",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Plus grande plateforme d'échange crypto au monde",
    },
    {
        "id": "kraken",
        "name": "Kraken",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Exchange américain réputé pour sa sécurité",
    },
]


def get_exchange_service(exchange: str) -> type[BaseExchangeService]:
    """Get exchange service class by exchange ID."""
    service_class = EXCHANGE_SERVICES.get(exchange.lower())
    if not service_class:
        raise ValueError(f"Exchange non supporté: {exchange}")
    return service_class


__all__ = [
    "BaseExchangeService",
    "BinanceService",
    "KrakenService",
    "CryptoComService",
    "EXCHANGE_SERVICES",
    "SUPPORTED_EXCHANGES",
    "get_exchange_service",
]
