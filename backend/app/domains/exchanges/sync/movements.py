from datetime import datetime
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeTrade, ExchangeWithdrawal
from app.domains.exchanges.sync.book import Book
from app.domains.exchanges.sync.pricing import market_price
from app.domains.exchanges.sync.rules import CREDITED, SENT, as_utc, cold_wallet_for, has_status
from app.domains.exchanges.sync.symbols import FIATS, base_symbol, conversion_base
from app.domains.portfolio.models import Asset
from app.domains.transactions.models import TransactionType
from app.domains.transactions.transfers import SAME_TRANSFER_TOLERANCE, create_mirror_transfer_in

SELL_PREFIX = "convert_sell_"
REWARD_QUOTES = ("EUR", "USD")


async def import_conversions(book: Book, conversions: list[ExchangeTrade]) -> None:
    for trade in conversions:
        if book.knows(trade.trade_id):
            continue
        symbol = conversion_base(trade.symbol, book.symbols)
        if symbol is None or symbol in FIATS:
            continue
        selling = trade.trade_id.startswith(SELL_PREFIX)
        await book.record(
            await book.asset(symbol),
            TransactionType.CONVERSION_OUT if selling else TransactionType.CONVERSION_IN,
            trade.quantity,
            (trade.price or Decimal("0")) if selling else Decimal("0"),
            executed_at=trade.timestamp,
            external_id=trade.trade_id,
            fee=trade.fee or Decimal("0"),
            fee_currency=trade.fee_currency,
            notes=(
                f"Conversion {symbol} -> autre crypto (trade_id:{trade.trade_id})"
                if selling
                else f"Conversion autre crypto -> {symbol} (trade_id:{trade.trade_id})"
            ),
        )


async def import_rewards(book: Book, rewards: list[ExchangeTrade]) -> None:
    for reward in rewards:
        symbol = next((reward.symbol[: -len(q)] for q in REWARD_QUOTES if reward.symbol.endswith(q)), reward.symbol)
        if book.knows(reward.trade_id) or base_symbol(symbol) in FIATS:
            continue
        staking = "staking" in reward.trade_id.lower()
        await book.record(
            await book.asset(symbol),
            TransactionType.STAKING_REWARD if staking else TransactionType.AIRDROP,
            reward.quantity,
            Decimal("0"),
            executed_at=reward.timestamp,
            external_id=reward.trade_id,
            notes=f"Reward from {book.exchange}",
        )


async def import_deposits(book: Book, deposits: list[ExchangeDeposit]) -> None:
    for deposit in deposits:
        external_id = f"deposit_{deposit.deposit_id}"
        if not has_status(deposit.status, CREDITED) or book.knows(external_id):
            continue
        if not deposit.symbol or base_symbol(deposit.symbol) in FIATS:
            continue
        asset = await book.asset(deposit.symbol)
        await book.record(
            asset,
            TransactionType.TRANSFER_IN,
            deposit.amount,
            await market_price(asset.symbol, asset.current_price),
            executed_at=deposit.timestamp,
            external_id=external_id,
            notes=f"Dépôt depuis externe ({deposit.tx_id[:16]}...)" if deposit.tx_id else "Dépôt externe",
        )


async def _entered_by_hand(book: Book, asset: Asset, moment: datetime, amount: Decimal) -> bool:
    return any(
        q > 0 and abs(q - amount) / q < SAME_TRANSFER_TOLERANCE for q in await book.withdrawn_around(asset, moment)
    )


async def import_withdrawals(
    book: Book, withdrawals: list[ExchangeWithdrawal], *, after: datetime, wallets: dict[str, str]
) -> None:
    """Retraits postérieurs à la dernière synchronisation : sortie de l'exchange et entrée miroir au wallet froid."""
    for withdrawal in withdrawals:
        external_id = f"withdrawal_{withdrawal.withdrawal_id}"
        moment = as_utc(withdrawal.timestamp)
        if not has_status(withdrawal.status, SENT) or moment is None or moment <= after or book.knows(external_id):
            continue
        asset = book.held(withdrawal.symbol) if withdrawal.symbol else None
        if asset is None or asset.symbol in FIATS or withdrawal.amount <= 0:
            continue
        if await _entered_by_hand(book, asset, moment, withdrawal.amount):
            book.remember(external_id)
            continue
        await book.refresh_cost(asset)
        destination = cold_wallet_for(withdrawal.address, wallets)
        transaction = await book.record(
            asset,
            TransactionType.TRANSFER_OUT,
            withdrawal.amount,
            asset.avg_buy_price,
            executed_at=moment,
            external_id=external_id,
            fee=withdrawal.fee or Decimal("0"),
            fee_currency=asset.symbol,
            notes=f"Retrait {book.exchange} → {destination}",
        )
        if transaction is not None:
            await create_mirror_transfer_in(book.session, transaction, asset, destination, amount_is_net=True)
