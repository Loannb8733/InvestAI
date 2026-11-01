"""Analyse des frais payés : total, par plateforme, par actif, par type, par mois."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.insights.periods import covered_months
from app.domains.market_data.fx.spot import FIAT_CURRENCIES
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset
from app.domains.transactions.models import Transaction, TransactionType

logger = logging.getLogger(__name__)

_TOP_ASSETS = 10
_RECENT_FEES = 20

EMPTY_FEES: dict[str, Any] = {
    "total_fees": 0,
    "nb_transactions_with_fees": 0,
    "nb_frais_non_convertis": 0,
    "avg_monthly_fee": 0,
    "by_exchange": {},
    "by_asset": {},
    "by_type": {},
    "by_month": {},
    "recent_fees": [],
}


@dataclass(frozen=True)
class FeeContext:
    """Ce qui permet de convertir un frais : l'actif échangé, la transaction, les cours des jetons."""

    asset_symbol: str
    price: float
    currency: str
    conversion_rate: float | None
    token_prices: dict[str, float] = field(default_factory=dict)


def fee_in_portfolio_currency(amount: float, fee_currency: str, context: FeeContext) -> tuple[float, bool]:
    """Montant en euros et s'il a pu être converti ; faute de cours, le montant reste tel quel, marqué non converti."""
    if amount <= 0:
        return 0.0, True
    currency = (fee_currency or "EUR").upper()
    if currency == "EUR":
        return amount, True
    tx_currency = (context.currency or "EUR").upper()
    rate = float(context.conversion_rate) if context.conversion_rate else (1.0 if tx_currency == "EUR" else None)
    if currency in FIAT_CURRENCIES:
        return (amount * rate, True) if currency == tx_currency and rate is not None else (amount, False)
    if currency == (context.asset_symbol or "").upper():
        return (amount * context.price * rate, True) if context.price > 0 and rate is not None else (amount, False)
    token_price = context.token_prices.get(currency, 0.0)
    return (amount * token_price, True) if token_price > 0 else (amount, False)


def _tokens_to_quote(transactions: Sequence[Transaction], assets: dict[str, Asset]) -> set[str]:
    tokens = set()
    for tx in transactions:
        token = (tx.fee_currency or "").upper()
        asset = assets.get(str(tx.asset_id))
        if (tx.fee_currency or "EUR").upper() not in FIAT_CURRENCIES and token != (
            asset.symbol.upper() if asset else ""
        ):
            tokens.add(token)
    return tokens


async def _token_prices(tokens: set[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for token in tokens:
        if not token:
            continue
        quote = await price_feed.quote(token, "crypto")
        if quote is None:
            logger.warning("Cours indisponible pour %s — frais laissés dans leur devise", token)
        else:
            prices[token] = float(quote.price)
    return prices


def _amount_of(tx: Transaction, context: FeeContext) -> tuple[float, bool]:
    if tx.transaction_type != TransactionType.FEE:
        return fee_in_portfolio_currency(float(tx.fee or 0), tx.fee_currency or "EUR", context)
    return fee_in_portfolio_currency(float(tx.quantity) * float(tx.price or 0), context.currency, context)


@dataclass
class _Tally:
    total: float = 0.0
    unconverted: int = 0
    by_exchange: dict[str, float] = field(default_factory=dict)
    by_asset: dict[str, float] = field(default_factory=dict)
    by_type: dict[str, float] = field(default_factory=dict)
    by_month: dict[str, float] = field(default_factory=dict)
    recent: list[dict[str, Any]] = field(default_factory=list)

    def add(self, tx: Transaction, asset: Asset | None, token_prices: dict[str, float]) -> None:
        symbol = asset.symbol if asset else "?"
        context = FeeContext(
            asset_symbol=asset.symbol if asset else "",
            price=float(tx.price or 0),
            currency=tx.currency or "EUR",
            conversion_rate=float(tx.conversion_rate) if tx.conversion_rate else None,
            token_prices=token_prices,
        )
        fee, converted = _amount_of(tx, context)
        self.unconverted += 0 if converted else 1
        self.total += fee
        exchange = tx.exchange or "Inconnu"
        kind = tx.transaction_type.value
        month = tx.executed_at.strftime("%Y-%m") if tx.executed_at else "?"
        self.by_exchange[exchange] = self.by_exchange.get(exchange, 0) + fee
        self.by_asset[symbol] = self.by_asset.get(symbol, 0) + fee
        self.by_type[kind] = self.by_type.get(kind, 0) + fee
        self.by_month[month] = self.by_month.get(month, 0) + fee
        self.recent.append(
            {
                "date": tx.executed_at.isoformat() if tx.executed_at else None,
                "symbol": symbol,
                "exchange": exchange,
                "type": kind,
                "fee": round(fee, 2),
                "fee_currency": tx.fee_currency or "EUR",
                "fee_convertie": converted,
            }
        )


def _rounded_by_amount(amounts: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 2) for key, value in sorted(amounts.items(), key=lambda item: -item[1])}


async def fee_analysis(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """Frais de l'utilisateur ; tant que `nb_frais_non_convertis` n'est pas nul, le total mélange des unités."""
    ids = await repository.portfolio_ids(db, user_id)
    assets = await repository.assets_of_portfolios(db, ids) if ids else {}
    if not assets:
        return {**EMPTY_FEES}
    transactions = await repository.transactions_with_fee(db, list(assets))
    token_prices = await _token_prices(_tokens_to_quote(transactions, assets))
    tally = _Tally()
    for tx in transactions:
        tally.add(tx, assets.get(str(tx.asset_id)), token_prices)
    return {
        "total_fees": round(tally.total, 2),
        "nb_transactions_with_fees": len(transactions),
        "nb_frais_non_convertis": tally.unconverted,
        "avg_monthly_fee": round(tally.total / covered_months(list(tally.by_month)), 2),
        "by_exchange": _rounded_by_amount(tally.by_exchange),
        "by_asset": dict(list(_rounded_by_amount(tally.by_asset).items())[:_TOP_ASSETS]),
        "by_type": _rounded_by_amount(tally.by_type),
        "by_month": {key: round(value, 2) for key, value in sorted(tally.by_month.items())},
        "recent_fees": tally.recent[:_RECENT_FEES],
    }
