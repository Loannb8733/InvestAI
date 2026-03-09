"""Quick state check."""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT count(*) FROM assets"))
        print(f"Total assets: {r.scalar()}")
        r = await db.execute(text("SELECT count(*) FROM transactions"))
        print(f"Total transactions: {r.scalar()}")
        r = await db.execute(text("SELECT count(*) FROM portfolios"))
        print(f"Total portfolios: {r.scalar()}")
        r = await db.execute(text("SELECT symbol, asset_type, quantity, exchange FROM assets ORDER BY symbol"))
        for row in r.all():
            print(f"  {row[0]:8s} | {row[1]:12s} | qty={float(row[2]):.8f} | {row[3]}")


if __name__ == "__main__":
    asyncio.run(main())
