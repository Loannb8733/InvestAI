"""Exchange services package."""

from app.services.exchanges.base import BaseExchangeService
from app.services.exchanges.binance import BinanceService
from app.services.exchanges.bitpanda import BitpandaService
from app.services.exchanges.bitstamp import BitstampService
from app.services.exchanges.bybit import BybitService
from app.services.exchanges.coinbase import CoinbaseService
from app.services.exchanges.cryptocom import CryptoComService
from app.services.exchanges.gateio import GateIOService
from app.services.exchanges.kraken import KrakenService
from app.services.exchanges.kucoin import KuCoinService
from app.services.exchanges.okx import OkxService

EXCHANGE_SERVICES = {
    "binance": BinanceService,
    "bitpanda": BitpandaService,
    "bitstamp": BitstampService,
    "bybit": BybitService,
    "coinbase": CoinbaseService,
    "cryptocom": CryptoComService,
    "gateio": GateIOService,
    "kraken": KrakenService,
    "kucoin": KuCoinService,
    "okx": OkxService,
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
        "id": "bitpanda",
        "name": "Bitpanda",
        "requires_secret": False,
        "requires_passphrase": False,
        "description": "Plateforme d'investissement européenne (crypto, actions, métaux)",
    },
    {
        "id": "bitstamp",
        "name": "Bitstamp",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "L'un des plus anciens exchanges crypto au monde",
    },
    {
        "id": "bybit",
        "name": "Bybit",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Exchange crypto avec trading de dérivés avancé",
    },
    {
        "id": "coinbase",
        "name": "Coinbase",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Exchange américain grand public avec Advanced Trade",
    },
    {
        "id": "cryptocom",
        "name": "Crypto.com",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Plateforme crypto populaire avec carte Visa et app mobile",
    },
    {
        "id": "gateio",
        "name": "Gate.io",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Exchange crypto avec un large choix d'altcoins",
    },
    {
        "id": "kraken",
        "name": "Kraken",
        "requires_secret": True,
        "requires_passphrase": False,
        "description": "Exchange américain réputé pour sa sécurité",
    },
    {
        "id": "kucoin",
        "name": "KuCoin",
        "requires_secret": True,
        "requires_passphrase": True,
        "description": "Exchange crypto populaire avec large choix d'altcoins",
    },
    {
        "id": "okx",
        "name": "OKX",
        "requires_secret": True,
        "requires_passphrase": True,
        "description": "Exchange crypto global avec trading spot et dérivés",
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
    "BitpandaService",
    "BitstampService",
    "BybitService",
    "CoinbaseService",
    "CryptoComService",
    "GateIOService",
    "KrakenService",
    "KuCoinService",
    "OkxService",
    "EXCHANGE_SERVICES",
    "SUPPORTED_EXCHANGES",
    "get_exchange_service",
]
