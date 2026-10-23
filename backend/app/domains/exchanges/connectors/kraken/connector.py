from app.domains.exchanges.connectors.kraken.derived import KrakenDerived
from app.domains.exchanges.connectors.kraken.trades import KrakenTrades


class KrakenService(KrakenTrades, KrakenDerived):
    pass
