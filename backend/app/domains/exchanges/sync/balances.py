import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.domains.exchanges.sync.book import Book, now
from app.domains.exchanges.sync.pricing import market_price
from app.domains.exchanges.sync.rules import balance_gap, undoes_recent_move
from app.domains.exchanges.sync.symbols import FIATS, Holdings, base_symbol
from app.domains.portfolio.models import Asset
from app.domains.transactions.ledger import ZERO
from app.domains.transactions.models import Transaction, TransactionType

logger = logging.getLogger(__name__)

RECENT_MOVES = timedelta(days=2)
EARN_TOLERANCE = Decimal("0.0001")


def _stamp(book: Book, step: str, symbol: str) -> str:
    return f"{book.exchange}_{step}_{symbol}_{int(now().timestamp())}"


async def _open_position(book: Book, symbol: str, quantity: Decimal) -> None:
    price = await market_price(symbol, None)
    await book.record(
        await book.asset(symbol),
        TransactionType.TRANSFER_IN,
        quantity,
        price,
        executed_at=now(),
        external_id=_stamp(book, "init", symbol),
        notes=f"Import initial depuis {book.exchange}",
    )


async def _adjust(book: Book, asset: Asset, theirs: Decimal) -> None:
    gap = theirs - asset.quantity
    if undoes_recent_move(gap, await book.moved_since(asset, now() - RECENT_MOVES)):
        logger.warning("%s : ajustement de %s ignoré, il annulerait un mouvement déjà enregistré", asset.symbol, gap)
    else:
        incoming = gap > 0
        await book.record(
            asset,
            TransactionType.TRANSFER_IN if incoming else TransactionType.TRANSFER_OUT,
            abs(gap),
            await market_price(asset.symbol, asset.current_price) if incoming else ZERO,
            executed_at=now(),
            external_id=_stamp(book, "sync", asset.symbol),
            notes=f"Ajustement balance {book.exchange}",
        )
    asset.quantity = theirs


async def _close_position(book: Book, asset: Asset) -> None:
    await book.record(
        asset,
        TransactionType.TRANSFER_OUT,
        asset.quantity,
        asset.avg_buy_price,
        executed_at=now(),
        external_id=_stamp(book, "zero", asset.symbol),
        notes=f"Solde zéro sur {book.exchange} (vendu/converti)",
    )
    asset.quantity = ZERO


async def _staking(book: Book) -> dict[str, tuple[Decimal, Transaction | None]]:
    query = (
        select(Transaction)
        .where(
            Transaction.asset_id.in_([a.id for a in book.assets]),
            Transaction.transaction_type.in_([TransactionType.STAKING, TransactionType.UNSTAKING]),
        )
        .order_by(Transaction.executed_at, Transaction.created_at)
    )
    positions: dict[str, tuple[Decimal, Transaction | None]] = {}
    for row in (await book.session.execute(query)).scalars():
        net, latest = positions.get(str(row.asset_id), (ZERO, None))
        if row.transaction_type == TransactionType.STAKING:
            positions[str(row.asset_id)] = (net + row.quantity, row)
        else:
            positions[str(row.asset_id)] = (net - row.quantity, latest)
    return positions


async def _mark_earn(book: Book, staked: dict[str, Decimal]) -> None:
    positions = await _staking(book)
    for asset in book.assets:
        net, latest = positions.get(str(asset.id), (ZERO, None))
        target = staked.get(asset.symbol, ZERO)
        change = target - net
        if abs(change) <= EARN_TOLERANCE:
            continue
        if change > 0 and net > 0 and latest is not None:
            latest.quantity += change
            latest.notes = f"Auto: {target:.8f} {asset.symbol} in Earn/Staking"
            latest.compute_hash()
            continue
        await book.record(
            asset,
            TransactionType.STAKING if change > 0 else TransactionType.UNSTAKING,
            abs(change),
            ZERO,
            executed_at=now(),
            notes=(
                f"Auto: {target:.8f} {asset.symbol} in Earn/Staking"
                if change > 0
                else f"Auto: sortie d'Earn/Staking ({abs(change):.8f} {asset.symbol})"
            ),
        )


async def reconcile(book: Book, held: Holdings) -> None:
    """Aligne les actifs sur les soldes de l'exchange, solde ceux qui en ont disparu et suit la part placée en Earn."""
    for symbol, theirs in held.totals.items():
        asset = book.held(symbol)
        if asset is None:
            if theirs > 0:
                await _open_position(book, symbol, theirs)
            continue
        gap = balance_gap(asset.quantity, theirs)
        if gap == "transfer":
            await _adjust(book, asset, theirs)
        elif gap == "dust":
            asset.quantity = theirs
    for asset in book.assets:
        gone = asset.symbol not in held.totals and asset.symbol not in FIATS
        if gone and asset.quantity > 0 and base_symbol(asset.symbol) == asset.symbol:
            await _close_position(book, asset)
    await _mark_earn(book, held.staked)
