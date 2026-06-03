"""Pure helpers for parsing exchange trading-pair symbols (FIN-01).

The exchange sync (`tasks/sync_exchanges.py`) historically booked every trade with
``currency="EUR"`` hard-coded, even when the executed price came from a USD/USDT pair
(e.g. ``BTCUSDT``). The cost-basis engine in ``metrics_service`` already supports a
per-transaction ``currency`` + ``conversion_rate`` (it stores ``unit_cost_base`` in the
trade currency and multiplies by ``fx_rate`` to reach the portfolio currency), so the
fix is purely upstream: detect the *quote* currency of each pair and record it.

This module is intentionally dependency-free and side-effect-free so it can be unit
tested deterministically (no DB / HTTP / Docker) and reused by both the live sync and
the historical backfill.

Sign / mapping conventions:
- ``split_pair("BTCUSDT")`` -> ``("BTC", "USDT")``.
- ``quote_fx_currency("USDT")`` -> ``"USD"`` (USD-pegged stables collapse to USD for FX).
- Unknown / unsplittable symbols return ``quote=None`` so callers can fall back safely
  rather than silently mis-currency a trade.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Quote currencies an exchange pair can be denominated in, ordered LONGEST-FIRST so
# that e.g. "USDT" matches before "USD" and "FDUSD" before "USD". Order within a length
# is irrelevant. Keep stablecoins explicit so we never strip a real base asset.
KNOWN_QUOTES: tuple[str, ...] = (
    # 5-char
    "FDUSD",
    # 4-char
    "USDT",
    "USDC",
    "BUSD",
    "TUSD",
    "EURT",
    "EURC",
    # 3-char
    "USD",
    "EUR",
    "GBP",
    "DAI",
    "BTC",
    "ETH",
    "BNB",
    "JPY",
    "CHF",
    "CAD",
    "AUD",
    # 4-char wrapped
    "USDP",
)

# Quote symbols that, for FX purposes, behave like a single fiat anchor. Cost basis
# only needs the *fiat* the trade was effectively priced in; the specific USD-pegged
# stablecoin does not change the EUR conversion.
_USD_PEGGED = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USD", "USDP"}
_EUR_PEGGED = {"EUR", "EURT", "EURC"}

# Crypto quotes (BTC/ETH/BNB pairs) are NOT fiat — converting their cost basis needs the
# quote asset's own price history, which is out of scope for the fiat-FX backfill.
CRYPTO_QUOTES = {"BTC", "ETH", "BNB"}


def split_pair(symbol: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a pair symbol into ``(base, quote)`` using a known-quote suffix match.

    Returns ``(None, None)`` for empty input, and ``(symbol, None)`` when no known
    quote suffix is found (e.g. an already-normalized bare asset like ``"BTC"``), so the
    caller can decide whether to treat it as base-only or skip it.
    """
    if not symbol:
        return (None, None)
    s = symbol.strip().upper()
    # Common separators used by some exchanges: BTC-USDT, BTC/USDT, BTC_USDT.
    for sep in ("-", "/", "_"):
        if sep in s:
            base, _, quote = s.partition(sep)
            base = base or None
            quote = quote or None
            return (base, quote)
    for quote in KNOWN_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            return (s[: -len(quote)], quote)
    # No recognizable quote suffix: treat the whole thing as the base asset.
    return (s, None)


def quote_fx_currency(quote: Optional[str]) -> Optional[str]:
    """Map a pair's quote currency to the fiat anchor used for FX conversion.

    USD-pegged stablecoins collapse to ``"USD"``; EUR-pegged to ``"EUR"``. Returns the
    quote unchanged for recognized fiats, and ``None`` for crypto or unknown quotes
    (signalling the caller it cannot do a simple fiat FX conversion).
    """
    if not quote:
        return None
    q = quote.strip().upper()
    if q in _USD_PEGGED:
        return "USD"
    if q in _EUR_PEGGED:
        return "EUR"
    if q in {"GBP", "JPY", "CHF", "CAD", "AUD"}:
        return q
    return None


def is_crypto_quote(quote: Optional[str]) -> bool:
    """True if the quote is a crypto asset (BTC/ETH/BNB), not a fiat anchor."""
    return bool(quote) and quote.strip().upper() in CRYPTO_QUOTES
