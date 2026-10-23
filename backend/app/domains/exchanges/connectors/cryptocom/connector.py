from app.domains.exchanges.connectors.cryptocom.balances import CryptoComBalances
from app.domains.exchanges.connectors.cryptocom.movements import CryptoComMovements
from app.domains.exchanges.connectors.cryptocom.trades import CryptoComTrades


class CryptoComService(CryptoComBalances, CryptoComTrades, CryptoComMovements):
    pass
