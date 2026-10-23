from app.domains.exchanges.connectors.base import BaseExchangeService
from app.domains.exchanges.connectors.binance.connector import BinanceService
from app.domains.exchanges.connectors.bitpanda import BitpandaService
from app.domains.exchanges.connectors.bitstamp.connector import BitstampService
from app.domains.exchanges.connectors.bybit.connector import BybitService
from app.domains.exchanges.connectors.coinbase.connector import CoinbaseService
from app.domains.exchanges.connectors.cryptocom.connector import CryptoComService
from app.domains.exchanges.connectors.gateio.connector import GateIOService
from app.domains.exchanges.connectors.kraken.connector import KrakenService
from app.domains.exchanges.connectors.kucoin.connector import KuCoinService
from app.domains.exchanges.connectors.okx import OkxService

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
