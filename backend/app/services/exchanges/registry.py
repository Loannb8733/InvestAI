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

EXCHANGE_SERVICES: dict[str, type[BaseExchangeService]] = {
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

_CATALOGUE = (
    ("binance", "Binance", True, False, "Plus grande plateforme d'échange crypto au monde"),
    ("bitpanda", "Bitpanda", False, False, "Plateforme d'investissement européenne (crypto, actions, métaux)"),
    ("bitstamp", "Bitstamp", True, False, "L'un des plus anciens exchanges crypto au monde"),
    ("bybit", "Bybit", True, False, "Exchange crypto avec trading de dérivés avancé"),
    ("coinbase", "Coinbase", True, False, "Exchange américain grand public avec Advanced Trade"),
    ("cryptocom", "Crypto.com", True, False, "Plateforme crypto populaire avec carte Visa et app mobile"),
    ("gateio", "Gate.io", True, False, "Exchange crypto avec un large choix d'altcoins"),
    ("kraken", "Kraken", True, False, "Exchange américain réputé pour sa sécurité"),
    ("kucoin", "KuCoin", True, True, "Exchange crypto populaire avec large choix d'altcoins"),
    ("okx", "OKX", True, True, "Exchange crypto global avec trading spot et dérivés"),
)

SUPPORTED_EXCHANGES = [
    {"id": key, "name": name, "requires_secret": secret, "requires_passphrase": passphrase, "description": text}
    for key, name, secret, passphrase, text in _CATALOGUE
]


def get_exchange_service(exchange: str) -> type[BaseExchangeService]:
    """Get exchange service class by exchange ID."""
    service_class = EXCHANGE_SERVICES.get(exchange.lower())
    if not service_class:
        raise ValueError(f"Exchange non supporté: {exchange}")
    return service_class
