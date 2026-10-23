from app.domains.exchanges.connectors.bybit.balances import BybitBalances
from app.domains.exchanges.connectors.bybit.trades import BybitTrades
from app.domains.exchanges.connectors.bybit.transfers import BybitTransfers


class BybitService(BybitBalances, BybitTrades, BybitTransfers):
    pass
