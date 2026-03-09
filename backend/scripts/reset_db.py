"""
Reset all investment data (assets, transactions) but keep users, API keys, and crowdfunding.

Run inside the backend container:
    python -m scripts.reset_db
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        # Show current state
        for table in ["transactions", "assets", "portfolios", "api_keys", "users"]:
            r = await db.execute(text(f"SELECT count(*) FROM {table}"))
            print(f"  {table}: {r.scalar()}")

        print("\n=== RESET: Suppression des transactions et assets (hors crowdfunding) ===\n")

        # 1. Delete all transactions
        r = await db.execute(text("DELETE FROM transactions"))
        print(f"  Transactions supprimées: {r.rowcount}")

        # 2. Delete non-crowdfunding assets
        r = await db.execute(text("DELETE FROM assets WHERE asset_type <> 'CROWDFUNDING'"))
        print(f"  Assets crypto supprimés: {r.rowcount}")

        # 3. Delete empty portfolios (no assets left)
        r = await db.execute(
            text(
                """
            DELETE FROM portfolios p
            WHERE NOT EXISTS (SELECT 1 FROM assets a WHERE a.portfolio_id = p.id)
        """
            )
        )
        print(f"  Portfolios vides supprimés: {r.rowcount}")

        # 4. Reset API key sync timestamps
        r = await db.execute(text("UPDATE api_keys SET last_sync_at = NULL"))
        print(f"  API keys reset: {r.rowcount}")

        await db.commit()

        # Show final state
        print("\n=== ÉTAT FINAL ===")
        for table in ["transactions", "assets", "portfolios", "api_keys", "users"]:
            r = await db.execute(text(f"SELECT count(*) FROM {table}"))
            print(f"  {table}: {r.scalar()}")

        # Show remaining assets (should be crowdfunding only)
        r = await db.execute(text("SELECT symbol, asset_type, quantity FROM assets"))
        for row in r.all():
            print(f"    → {row[0]} ({row[1]}) qty={float(row[2])}")


if __name__ == "__main__":
    asyncio.run(main())
