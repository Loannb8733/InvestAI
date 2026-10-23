DASHBOARD_BENCHMARKS = (("Bitcoin", "BTC", "crypto"), ("S&P 500", "SPY", "etf"), ("MSCI World", "IWDA.AS", "etf"))
ANALYTICS_BENCHMARKS = (("S&P500", "^GSPC", "stock"), ("Nasdaq", "^IXIC", "stock"), ("Gold", "PAXG", "crypto"))
MARKET_REFERENCES = tuple((symbol, kind) for _, symbol, kind in DASHBOARD_BENCHMARKS + ANALYTICS_BENCHMARKS)
