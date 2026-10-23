from app.domains.exchanges.connectors.gateio.balances import GateIOBalances
from app.domains.exchanges.connectors.gateio.trades import GateIOTrades
from app.domains.exchanges.connectors.gateio.transfers import GateIOTransfers


class GateIOService(GateIOBalances, GateIOTrades, GateIOTransfers):
    pass
