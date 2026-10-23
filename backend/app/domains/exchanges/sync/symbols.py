import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from app.domains.exchanges.sync.pairs import split_pair
from app.services.exchanges.base import ExchangeBalance

logger = logging.getLogger(__name__)

FIATS = frozenset({"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "TRY", "RUB", "UAH", "BRL"})
WRAPPED = {
    "WBTC": "BTC",
    "WETH": "ETH",
    "WBETH": "BETH",
    "WBNB": "BNB",
    "WSOL": "SOL",
    "WMATIC": "MATIC",
    "WAVAX": "AVAX",
    "WSTETH": "STETH",
    "WFTM": "FTM",
    "WPOL": "POL",
}
EARN_PREFIXES = ("LD", "BF")
EARN_BASES = (
    "ADA",
    "SUI",
    "XRP",
    "FET",
    "ETH",
    "BTC",
    "SOL",
    "TAO",
    "OM",
    "PENDLE",
    "LINK",
    "ONDO",
    "INJ",
    "KAITO",
    "DOGE",
    "USDC",
    "USDT",
)
EARN_SUFFIXES = frozenset({"U", "S", "KA", "US"})


def earn_base(symbol: str) -> str | None:
    """Actif placé derrière une variante Earn (LDBTC, ADAU, OMKA), par préfixes et suffixes énumérés."""
    for prefix in EARN_PREFIXES:
        if symbol.startswith(prefix) and len(symbol) > len(prefix) + 2:
            return symbol[len(prefix) :]
    for base in EARN_BASES:
        if symbol.startswith(base) and symbol[len(base) :] in EARN_SUFFIXES:
            return base
    return None


def base_symbol(symbol: str) -> str:
    """Symbole de l'actif détenu : variantes wrapped et Earn ramenées à leur sous-jacent."""
    return WRAPPED.get(symbol) or earn_base(symbol) or symbol


def _known_prefix(symbol: str, known: Iterable[str]) -> str | None:
    text = base_symbol(symbol)
    return next((c for c in sorted(known, key=len, reverse=True) if text.startswith(c)), None)


def conversion_base(symbol: str, known: Iterable[str]) -> str | None:
    """Actif connu le plus long qui préfixe le symbole d'une conversion ; aucun n'est deviné."""
    found = _known_prefix(symbol, known)
    if found is None:
        logger.warning("Conversion ignorée : aucun actif connu ne correspond au symbole %s", symbol)
    return found


def trade_base(symbol: str, known: Iterable[str]) -> tuple[str | None, str | None]:
    """Actif et cotation d'une paire ; sans cotation connue, l'actif connu qui la préfixe."""
    base, quote = split_pair(symbol)
    if quote is None:
        base = _known_prefix(symbol, known) if symbol else None
    if base is None:
        return None, quote
    base = base_symbol(base)
    return (None, quote) if base in FIATS else (base, quote)


@dataclass
class Holdings:
    """Soldes d'un exchange par actif détenu, et la part placée en Earn."""

    totals: dict[str, Decimal] = field(default_factory=dict)
    staked: dict[str, Decimal] = field(default_factory=dict)


def holdings(balances: Iterable[ExchangeBalance]) -> Holdings:
    """Fond les variantes dans leur actif ; les devises fiat sont écartées."""
    result = Holdings()
    for balance in balances:
        base = base_symbol(balance.symbol)
        if balance.symbol in FIATS or base in FIATS:
            continue
        result.totals[base] = result.totals.get(base, Decimal("0")) + balance.total
        if earn_base(balance.symbol) is not None:
            result.staked[base] = result.staked.get(base, Decimal("0")) + balance.total
    return result
