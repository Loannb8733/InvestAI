from app.domains.exchanges.connectors.bitstamp.balances import BitstampBalances
from app.domains.exchanges.connectors.bitstamp.movements import BitstampMovements
from app.domains.exchanges.connectors.bitstamp.trades import BitstampTrades


class BitstampService(BitstampBalances, BitstampTrades, BitstampMovements):
    """Connecteur Bitstamp (API v2), signé en HMAC SHA256 dans les en-têtes X-Auth."""
