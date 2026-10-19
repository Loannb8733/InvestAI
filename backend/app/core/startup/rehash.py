import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def rehash_transactions_internal_hash(factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    try:
        from sqlalchemy import select

        from app.core.db.session import session_factory
        from app.models.transaction import Transaction, compute_transaction_hash

        fabrique = factory or session_factory
        async with fabrique() as db:
            result = await db.execute(select(Transaction))
            txs = result.scalars().all()

            seen: dict = {}
            a_ecrire: list = []
            a_liberer: list = []
            for tx in txs:
                ts = tx.executed_at.strftime("%Y-%m-%d") if tx.executed_at else ""
                ttype = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
                target = compute_transaction_hash(
                    asset_id=str(tx.asset_id),
                    transaction_type=ttype,
                    quantity=str(tx.quantity),
                    price=str(tx.price),
                    executed_at=ts,
                )
                if target in seen:
                    if tx.internal_hash is not None:
                        a_liberer.append(tx)
                    continue
                seen[target] = tx.id
                if tx.internal_hash != target:
                    a_ecrire.append((tx, target))

            if a_liberer:
                for tx in a_liberer:
                    tx.internal_hash = None
                await db.commit()
            if a_ecrire:
                for tx, target in a_ecrire:
                    tx.internal_hash = target
                await db.commit()

            if a_ecrire or a_liberer:
                logger.info(
                    "Rehashed transactions: %d updated, %d nulled on collision",
                    len(a_ecrire),
                    len(a_liberer),
                )
    except Exception as e:
        logger.error("Transaction rehash FAILED (deduplication left stale): %s", e, exc_info=True)
