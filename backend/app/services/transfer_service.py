"""Service for handling mirror transfer transactions."""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.transaction import Transaction, TransactionType

logger = logging.getLogger(__name__)


async def create_mirror_transfer_in(
    db: AsyncSession,
    source_transaction: Transaction,
    source_asset: Asset,
    destination_exchange: str,
) -> Transaction:
    """Create a mirror transfer_in on the destination platform.

    When a user transfers crypto from an exchange to a cold wallet,
    this creates the corresponding transfer_in on the destination asset.

    Args:
        db: Database session.
        source_transaction: The transfer_out transaction.
        source_asset: The asset on the source exchange.
        destination_exchange: Name of the destination platform (e.g. "Tangem").

    Returns:
        The created mirror transfer_in transaction.
    """
    # Find or create destination asset
    result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id == source_asset.portfolio_id,
            Asset.symbol == source_asset.symbol,
            Asset.exchange == destination_exchange,
        )
    )
    dest_asset = result.scalar_one_or_none()

    if not dest_asset:
        dest_asset = Asset(
            portfolio_id=source_asset.portfolio_id,
            symbol=source_asset.symbol,
            name=source_asset.name,
            asset_type=source_asset.asset_type,
            quantity=Decimal("0"),
            avg_buy_price=Decimal("0"),
            exchange=destination_exchange,
            currency=source_asset.currency,
        )
        db.add(dest_asset)
        await db.flush()
        logger.info(
            "Created destination asset %s/%s (id=%s)",
            source_asset.symbol,
            destination_exchange,
            dest_asset.id,
        )

    # Mirror quantity: subtract network fee if fee is in the same asset
    qty = Decimal(str(source_transaction.quantity))
    fee = Decimal(str(source_transaction.fee or 0))
    fee_currency = (source_transaction.fee_currency or "").upper()
    symbol = source_asset.symbol.upper()

    # Network fees are paid in the transferred asset
    if fee > 0 and (not fee_currency or fee_currency == symbol):
        mirror_qty = qty - fee
    else:
        mirror_qty = qty

    if mirror_qty <= 0:
        logger.warning(
            "Mirror quantity <= 0 for %s transfer_out (qty=%s, fee=%s), skipping",
            symbol,
            qty,
            fee,
        )
        return None

    mirror = Transaction(
        asset_id=dest_asset.id,
        transaction_type=TransactionType.TRANSFER_IN,
        quantity=mirror_qty,
        price=source_transaction.price,
        fee=Decimal("0"),
        currency=source_transaction.currency,
        executed_at=source_transaction.executed_at,
        exchange=destination_exchange,
        notes=f"Auto-mirror from {source_asset.exchange or 'unknown'}",
        related_transaction_id=source_transaction.id,
    )
    mirror.compute_hash()
    db.add(mirror)
    await db.flush()

    # Link source → mirror
    source_transaction.related_transaction_id = mirror.id

    # Update destination asset quantity
    dest_asset.quantity = Decimal(str(dest_asset.quantity)) + mirror_qty

    logger.info(
        "Created mirror transfer_in %s %s on %s (id=%s)",
        mirror_qty,
        symbol,
        destination_exchange,
        mirror.id,
    )

    return mirror
