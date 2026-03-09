"""Audit transaction integrity."""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        # 1. Quantité stockée vs calculée depuis transactions
        r = await db.execute(
            text(
                """
            SELECT a.symbol, a.quantity as stored_qty,
                   COALESCE(SUM(CASE
                       WHEN t.transaction_type IN ('BUY','TRANSFER_IN','AIRDROP','STAKING_REWARD','CONVERSION_IN','DIVIDEND','INTEREST') THEN t.quantity
                       WHEN t.transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT','FEE') THEN -t.quantity
                       ELSE 0 END), 0) as computed_qty
            FROM assets a
            LEFT JOIN transactions t ON t.asset_id = a.id
            WHERE a.asset_type <> 'CROWDFUNDING'
            GROUP BY a.symbol, a.quantity, a.id
            ORDER BY a.symbol
        """
            )
        )
        print("=== QUANTITE STOCKEE vs CALCULEE ===")
        mismatches = []
        for row in r.all():
            stored = float(row[1])
            computed = float(row[2])
            diff = abs(stored - computed)
            flag = " !!!" if diff > 0.00000001 else " ok"
            print(f"  {row[0]:8s} | stocke={stored:>16.8f} | calcule={computed:>16.8f} | diff={diff:.8f}{flag}")
            if diff > 0.00000001:
                mismatches.append(row[0])

        if mismatches:
            print(f"\n  ATTENTION: {len(mismatches)} assets avec ecart: {', '.join(mismatches)}")
        else:
            print("\n  Toutes les quantites sont coherentes.")

        # 2. BUY/SELL avec prix=0
        r = await db.execute(
            text(
                """
            SELECT a.symbol, t.transaction_type, t.quantity, t.price, t.executed_at
            FROM transactions t JOIN assets a ON a.id = t.asset_id
            WHERE t.price = 0 AND t.transaction_type IN ('BUY','SELL')
            ORDER BY t.executed_at
        """
            )
        )
        rows = r.all()
        print(f"\n=== BUY/SELL AVEC PRIX=0: {len(rows)} ===")
        for row in rows[:10]:
            print(f"  {row[0]} | {row[1]} | qty={float(row[2]):.8f} | {str(row[4])[:10]}")

        # 3. Valeur investie
        r = await db.execute(
            text(
                """
            SELECT SUM(a.quantity * a.avg_buy_price)
            FROM assets a
            WHERE a.asset_type <> 'CROWDFUNDING' AND a.quantity > 0
        """
            )
        )
        print(f"\n=== VALEUR INVESTIE (qty x avg_buy_price): {float(r.scalar() or 0):.2f} EUR ===")

        # 4. Transactions avec dates NULL
        r = await db.execute(
            text(
                """
            SELECT a.symbol, t.transaction_type, t.quantity, t.price
            FROM transactions t JOIN assets a ON a.id = t.asset_id
            WHERE t.executed_at IS NULL
            ORDER BY a.symbol
        """
            )
        )
        rows = r.all()
        print(f"\n=== TRANSACTIONS SANS DATE: {len(rows)} ===")
        for row in rows:
            print(f"  {row[0]} | {row[1]} | qty={float(row[2]):.8f} | price={float(row[3]):.8f}")

        # 5. Résumé final
        r = await db.execute(text("SELECT count(*) FROM transactions"))
        total = r.scalar()
        r = await db.execute(text("SELECT count(*) FROM transactions WHERE internal_hash IS NULL"))
        no_hash = r.scalar()
        r = await db.execute(
            text(
                """
            SELECT count(*) FROM (
                SELECT internal_hash FROM transactions
                WHERE internal_hash IS NOT NULL
                GROUP BY internal_hash HAVING count(*) > 1
            ) dups
        """
            )
        )
        dup_hashes = r.scalar()
        print(f"\n=== RESUME ===")
        print(f"  Total transactions: {total}")
        print(f"  Sans hash: {no_hash}")
        print(f"  Hash en doublon: {dup_hashes}")


if __name__ == "__main__":
    asyncio.run(main())
