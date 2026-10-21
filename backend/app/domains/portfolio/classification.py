FIAT_SYMBOLS = frozenset({"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"})

STABLECOIN_PEGS: dict[str, str] = {
    "USDT": "USD",
    "USDC": "USD",
    "BUSD": "USD",
    "DAI": "USD",
    "TUSD": "USD",
    "USDP": "USD",
    "GUSD": "USD",
    "FRAX": "USD",
    "LUSD": "USD",
    "USDG": "USD",
    "USDD": "USD",
    "PYUSD": "USD",
    "FDUSD": "USD",
    "EURT": "EUR",
    "EURC": "EUR",
    "EUROC": "EUR",
}

STABLECOIN_SYMBOLS = frozenset(STABLECOIN_PEGS)
SAFE_HAVEN_SYMBOLS = frozenset({"PAXG", "XAUT", "GLD", "IAU", "SGOL", "GOLD"})


def is_fiat(symbol: str) -> bool:
    return symbol.upper() in FIAT_SYMBOLS


def is_stablecoin(symbol: str) -> bool:
    """Stablecoin connu ; ``STABLECOIN_PEGS`` donne la monnaie qu'il suit."""
    return symbol.upper() in STABLECOIN_SYMBOLS


def is_cash_like(symbol: str) -> bool:
    """Monnaie ou stablecoin : compté en trésorerie, hors des métriques d'investissement."""
    return is_fiat(symbol) or is_stablecoin(symbol)


def is_safe_haven(symbol: str) -> bool:
    """Jeton adossé à l'or ou ETF or."""
    return symbol.upper() in SAFE_HAVEN_SYMBOLS
