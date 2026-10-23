from app.domains.exchanges.connectors.binance.balances import BinanceBalances
from app.domains.exchanges.connectors.binance.conversions import BinanceConversions
from app.domains.exchanges.connectors.binance.earn import BinanceEarn
from app.domains.exchanges.connectors.binance.fiat import BinanceFiat
from app.domains.exchanges.connectors.binance.trades import BinanceTrades
from app.domains.exchanges.connectors.binance.transfers import BinanceTransfers


class BinanceService(BinanceBalances, BinanceTrades, BinanceTransfers, BinanceFiat, BinanceConversions, BinanceEarn):
    pass
