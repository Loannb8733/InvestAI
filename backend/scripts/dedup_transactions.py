"""
Deduplicate transactions and backfill internal_hash.

Run inside the backend container:
    python -m scripts.dedup_transactions

Steps:
1. Backfill internal_hash for all existing transactions
2. Detect duplicates (same hash)
3. Keep the oldest transaction per hash, delete the rest
4. Report results
"""

import asyncio
import sys
from collections import defaultdict

# Add parent dir so we can import app modules
sys.path.insert(0, "/app")

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.transaction import Transaction, compute_transaction_hash


async def main():
    async with AsyncSessionLocal() as db:
        # Step 0: Clear all existing hashes (formula changed)
        from sqlalchemy import update

        await db.execute(update(Transaction).values(internal_hash=None))
        await db.commit()
        print("Cleared all existing hashes (formula v2: date-only, no exchange/external_id).\n")

        # Step 1: Load all transactions
        result = await db.execute(
            select(
                Transaction.id,
                Transaction.asset_id,
                Transaction.transaction_type,
                Transaction.quantity,
                Transaction.price,
                Transaction.executed_at,
                Transaction.exchange,
                Transaction.external_id,
                Transaction.internal_hash,
                Transaction.created_at,
            ).order_by(Transaction.created_at.asc())
        )
        rows = result.all()
        print(f"Total transactions: {len(rows)}")

        # Step 2: Compute hashes and find duplicates
        hash_groups = defaultdict(list)
        needs_update = []

        for row in rows:
            ts = ""
            if row.executed_at:
                ts = (
                    row.executed_at.strftime("%Y-%m-%d")
                    if hasattr(row.executed_at, "strftime")
                    else str(row.executed_at)[:10]
                )

            h = compute_transaction_hash(
                asset_id=str(row.asset_id),
                transaction_type=row.transaction_type.value
                if hasattr(row.transaction_type, "value")
                else str(row.transaction_type),
                quantity=str(row.quantity),
                price=str(row.price),
                executed_at=ts,
            )

            hash_groups[h].append(
                {
                    "id": row.id,
                    "created_at": row.created_at,
                    "current_hash": row.internal_hash,
                    "external_id": row.external_id,
                    "exchange": row.exchange,
                }
            )

            if row.internal_hash != h:
                needs_update.append((row.id, h))

        # Step 3: Identify duplicates
        duplicates = {h: txs for h, txs in hash_groups.items() if len(txs) > 1}
        total_dupes = sum(len(txs) - 1 for txs in duplicates.values())
        print(f"Unique hashes: {len(hash_groups)}")
        print(f"Duplicate groups: {len(duplicates)}")
        print(f"Duplicate transactions to remove: {total_dupes}")

        if duplicates:
            print("\nDuplicate details:")
            for h, txs in list(duplicates.items())[:20]:  # Show first 20
                print(f"  Hash {h[:12]}... → {len(txs)} copies")

        # Step 4: Delete duplicates (prefer keeping exchange-synced version)
        ids_to_delete = []
        for h, txs in duplicates.items():
            # Prefer tx with external_id (exchange-synced), then oldest
            sorted_txs = sorted(
                txs,
                key=lambda t: (
                    0 if t.get("external_id") and t["external_id"] not in ("", "-") else 1,
                    t["created_at"] or "",
                ),
            )
            for tx in sorted_txs[1:]:
                ids_to_delete.append(tx["id"])

        if ids_to_delete:
            print(f"\nDeleting {len(ids_to_delete)} duplicate transactions...")
            # Delete in batches of 500
            for i in range(0, len(ids_to_delete), 500):
                batch = ids_to_delete[i : i + 500]
                await db.execute(delete(Transaction).where(Transaction.id.in_(batch)))
            await db.commit()
            print("Duplicates deleted.")
        else:
            print("\nNo duplicates found.")

        # Step 5: Backfill internal_hash for remaining transactions
        # Re-query to get the surviving transactions
        remaining = await db.execute(
            select(Transaction.id, Transaction.internal_hash).where(Transaction.internal_hash.is_(None))
        )
        to_update = remaining.all()

        if to_update:
            print(f"\nBackfilling internal_hash for {len(to_update)} transactions...")
            # Reload full data for hash computation
            for tx_id, _ in to_update:
                tx_result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
                tx = tx_result.scalar_one_or_none()
                if tx:
                    tx.compute_hash()

            await db.commit()
            print("Hash backfill complete.")
        else:
            print("\nAll transactions already have hashes.")

        # Final count
        final_count = await db.execute(select(func.count()).select_from(Transaction))
        print(f"\nFinal transaction count: {final_count.scalar()}")


if __name__ == "__main__":
    asyncio.run(main())
