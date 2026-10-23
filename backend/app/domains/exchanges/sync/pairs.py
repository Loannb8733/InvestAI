KNOWN_QUOTES = (
    "FDUSD",
    "USDT",
    "USDC",
    "BUSD",
    "TUSD",
    "EURT",
    "EURC",
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
    "USDP",
)
USD_PEGGED = frozenset({"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USD", "USDP"})
EUR_PEGGED = frozenset({"EUR", "EURT", "EURC"})
OTHER_FIATS = frozenset({"GBP", "JPY", "CHF", "CAD", "AUD"})


def split_pair(symbol: str) -> tuple[str | None, str | None]:
    """Sépare une paire en (base, cotation) ; la cotation est None quand aucun suffixe connu ne correspond."""
    if not symbol:
        return None, None
    text = symbol.strip().upper()
    for separator in ("-", "/", "_"):
        if separator in text:
            head, _, tail = text.partition(separator)
            return head or None, tail or None
    for quote in KNOWN_QUOTES:
        if text.endswith(quote) and len(text) > len(quote):
            return text[: -len(quote)], quote
    return text, None


def fiat_anchor(quote: str | None) -> str | None:
    """Devise fiat de référence d'une cotation : USD pour les stablecoins dollar, None pour une crypto."""
    if not quote:
        return None
    text = quote.strip().upper()
    if text in USD_PEGGED:
        return "USD"
    if text in EUR_PEGGED:
        return "EUR"
    return text if text in OTHER_FIATS else None
