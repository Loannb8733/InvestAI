"""Asset symbol classification helpers.

Pure, dependency-free predicates extracted from ``metrics_service`` so the many
call sites (metrics, snapshots, analytics, reports) can import them without
pulling in the whole metrics god-module. ``metrics_service`` re-exports these for
backwards compatibility.
"""

# Fiat currencies -> counted as cash
FIAT_SYMBOLS = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"}

# Stablecoins -> separate card, excluded from investment metrics
STABLECOIN_SYMBOLS = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "USDP",
    "GUSD",
    "FRAX",
    "LUSD",
    "USDG",
    "PYUSD",
    "FDUSD",
    "EURC",
    "EURT",
}

# Gold / safe-haven assets
_GOLD_SYMBOLS = {"PAXG", "XAUT", "GLD", "IAU", "SGOL", "GOLD"}


def is_fiat(symbol: str) -> bool:
    return symbol.upper() in FIAT_SYMBOLS


def is_stablecoin(symbol: str) -> bool:
    return symbol.upper() in STABLECOIN_SYMBOLS


def is_cash_like(symbol: str) -> bool:
    return is_fiat(symbol) or is_stablecoin(symbol)


# Canonical alias — use this across the codebase
is_liquidity = is_cash_like


def is_safe_haven(symbol: str) -> bool:
    """Return True for gold-backed tokens and ETFs."""
    return symbol.upper() in _GOLD_SYMBOLS
