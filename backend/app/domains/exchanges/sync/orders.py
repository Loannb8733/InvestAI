from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeFiatOrder, ExchangeTrade
from app.domains.exchanges.sync.book import Book
from app.domains.exchanges.sync.feed import Feed
from app.domains.exchanges.sync.pricing import TradeFx
from app.domains.exchanges.sync.symbols import FIATS, trade_base
from app.domains.transactions.models import TransactionType


@dataclass(frozen=True)
class Order:
    """Achat ou vente d'une crypto contre une devise, quelle que soit sa source chez l'exchange."""

    external_ids: tuple[str, ...]
    symbol: str | None
    quote: str | None
    kind: TransactionType
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str | None
    executed_at: datetime
    notes: str | None


def _side(side: str) -> TransactionType:
    return TransactionType.BUY if side == "buy" else TransactionType.SELL


def _from_trade(book: Book, trade: ExchangeTrade, notes: str | None, *, buy_only: bool = False) -> Order:
    symbol, quote = trade_base(trade.symbol, book.symbols)
    return Order(
        external_ids=(trade.trade_id,),
        symbol=symbol,
        quote=quote,
        kind=TransactionType.BUY if buy_only else _side(trade.side),
        quantity=trade.quantity,
        price=trade.price or Decimal("0"),
        fee=trade.fee or Decimal("0"),
        fee_currency=trade.fee_currency,
        executed_at=trade.timestamp,
        notes=notes,
    )


def _from_fiat(order: ExchangeFiatOrder) -> Order:
    symbol = order.crypto_symbol if order.crypto_symbol and order.crypto_symbol not in FIATS else None
    note = "Auto-Invest DCA" if order.order_id.startswith("autoinvest_") else "Fiat Order"
    return Order(
        external_ids=(f"fiat_{order.order_id}", order.order_id),
        symbol=symbol,
        quote=order.fiat_currency,
        kind=_side(order.side),
        quantity=order.crypto_amount,
        price=order.price or Decimal("0"),
        fee=order.fee or Decimal("0"),
        fee_currency=order.fiat_currency,
        executed_at=order.timestamp,
        notes=note,
    )


def orders(book: Book, feed: Feed) -> list[Order]:
    """Ordres de l'historique, dans l'ordre où ils sont importés : avant les conversions qui s'y réfèrent."""
    return [
        *(_from_trade(book, t, None) for t in feed.trades),
        *(_from_trade(book, t, "Instant Buy", buy_only=True) for t in feed.instant_buys),
        *(_from_fiat(o) for o in feed.fiat_orders),
    ]


async def import_orders(book: Book, fx: TradeFx, items: list[Order]) -> None:
    for order in items:
        if order.symbol is None or book.knows(*order.external_ids):
            continue
        currency, rate = await fx.resolve(order.quote, order.executed_at)
        await book.record(
            await book.asset(order.symbol),
            order.kind,
            order.quantity,
            order.price,
            executed_at=order.executed_at,
            external_id=order.external_ids[0],
            currency=currency,
            rate=rate,
            fee=order.fee,
            fee_currency=order.fee_currency,
            notes=order.notes,
        )


async def repair_orders(book: Book, fx: TradeFx, items: list[Order]) -> int:
    """Recalcul FX : devise et taux du jour reposés sur les ordres déjà importés, sans rien écrire d'autre."""
    repaired = 0
    for order in items:
        if not book.knows(*order.external_ids):
            continue
        currency, rate = await fx.resolve(order.quote, order.executed_at)
        if await book.repair(order.external_ids, order.price, currency, rate):
            repaired += 1
    return repaired
