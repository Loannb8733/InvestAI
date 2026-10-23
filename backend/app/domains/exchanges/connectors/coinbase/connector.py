from app.domains.exchanges.connectors.coinbase.balances import CoinbaseBalances
from app.domains.exchanges.connectors.coinbase.movements import CoinbaseMovements
from app.domains.exchanges.connectors.coinbase.trades import CoinbaseTrades


class CoinbaseService(CoinbaseBalances, CoinbaseTrades, CoinbaseMovements):
    pass
