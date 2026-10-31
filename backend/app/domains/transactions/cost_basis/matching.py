"""Rapprochement d'une conversion sortante avec sa conversion entrante."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domains.transactions.cost_basis.context import ONE, ReplayContext
from app.domains.transactions.cost_basis.layers import ZERO

_SELL_TRADE_ID = re.compile(r"trade_id:convert_sell_(\S+)")
_SELL_PREFIX = "convert_sell_"


@dataclass(frozen=True)
class ConversionMatch:
    """Destination trouvée ; `symbol` vaut None sans correspondance."""

    symbol: str | None
    exchange: str | None
    quantity: Decimal
    price: Decimal


def price_in_portfolio_currency(price: Any, conversion_rate: Any) -> Decimal:
    """Prix enregistré exprimé dans la devise du portefeuille."""
    amount = Decimal(str(price or 0))
    rate = Decimal(str(conversion_rate)) if conversion_rate else ONE
    return amount * rate


def _leg(entry: Any, symbol: str) -> ConversionMatch:
    return ConversionMatch(
        symbol=symbol,
        exchange=(entry.exchange or "").strip(),
        quantity=Decimal(str(entry.quantity)),
        price=price_in_portfolio_currency(entry.price, getattr(entry, "conversion_rate", None)),
    )


def _match_crypto_com(ctx: ReplayContext, tx: Any) -> ConversionMatch | None:
    notes = tx.notes or ""
    exchange = tx.exchange or ""
    for entry in ctx.conversion_ins:
        if (entry.notes or "") == notes and (entry.exchange or "") == exchange:
            return _leg(entry, ctx.aid_to_symbol.get(str(entry.asset_id), ""))
    return None


def _first_distinct_leg(
    ctx: ReplayContext,
    tx: Any,
    source: str,
    suffix: str,
    is_leg: Callable[[Any], bool],
    rejection: str,
) -> ConversionMatch | None:
    for entry in ctx.conversion_ins:
        if not is_leg(entry):
            continue
        candidate = ctx.aid_to_symbol.get(str(entry.asset_id), "")
        if candidate and candidate != source:
            return _leg(entry, candidate)
        ctx.warn(rejection, source, candidate, suffix, tx.id)
        return None
    return None


def _match_by_notes(ctx: ReplayContext, tx: Any, source: str) -> ConversionMatch | None:
    found = _SELL_TRADE_ID.search(tx.notes or "")
    if found is None:
        return None
    suffix = found.group(1)
    return _first_distinct_leg(
        ctx,
        tx,
        source,
        suffix,
        lambda entry: f"convert_buy_{suffix}" in (entry.notes or ""),
        "Conversion match rejected: src=%s == dest=%s (suffix=%s, tx_id=%s)",
    )


def _match_by_external_id(ctx: ReplayContext, tx: Any, source: str) -> ConversionMatch | None:
    external_id = getattr(tx, "external_id", None) or ""
    if not external_id.startswith(_SELL_PREFIX):
        return None
    suffix = external_id[len(_SELL_PREFIX) :]
    return _first_distinct_leg(
        ctx,
        tx,
        source,
        suffix,
        lambda entry: (getattr(entry, "external_id", None) or "") == f"convert_buy_{suffix}",
        "Conversion match (ext_id fallback) rejected: src=%s == dest=%s (suffix=%s, tx_id=%s)",
    )


def match_conversion_in(ctx: ReplayContext, tx: Any, source: str) -> ConversionMatch:
    """Trouve la conversion entrante d'une sortie : mêmes notes chez Crypto.com, identifiant d'échange ailleurs."""
    if "crypto.com" in (tx.exchange or "").lower():
        match = _match_crypto_com(ctx, tx)
    else:
        match = _match_by_notes(ctx, tx, source)
        if match is None and ctx.config.conversion_external_id_fallback:
            match = _match_by_external_id(ctx, tx, source)
    return match or ConversionMatch(None, None, Decimal(str(tx.quantity)), ZERO)
