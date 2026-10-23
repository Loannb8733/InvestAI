from app.domains.exchanges.connectors.kucoin.balances import KuCoinBalances
from app.domains.exchanges.connectors.kucoin.movements import KuCoinMovements
from app.domains.exchanges.connectors.kucoin.trades import KuCoinTrades


class KuCoinService(KuCoinBalances, KuCoinTrades, KuCoinMovements):
    pass
