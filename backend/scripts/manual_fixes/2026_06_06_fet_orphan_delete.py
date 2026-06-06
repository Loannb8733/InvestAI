"""Supprime le SELL FET orphelin (import manuel ancien sans jumeau)."""

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TARGET_TX_ID = "2afc8ce9"  # prefix-match au cas où; on resolve complet ci-dessous


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    return url


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    async with eng.connect() as conn:
        # Resolve the exact transaction matching the orphan profile
        rows = (
            (
                await conn.execute(
                    text(
                        """
            SELECT t.id::text AS tx_id, a.symbol, t.transaction_type::text AS type,
                   t.quantity, t.executed_at, t.created_at, t.notes
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE a.symbol = 'FET'
              AND a.exchange = 'Binance'
              AND t.exchange = 'Binance'
              AND t.transaction_type = 'SELL'
              AND (t.external_id IS NULL OR t.external_id = '')
              AND t.notes LIKE 'Spot trade FET/USDC #182676642%'
        """
                    )
                )
            )
            .mappings()
            .all()
        )

        if not rows:
            print("Target transaction NOT found — already deleted, or selector outdated.")
            return 0
        if len(rows) > 1:
            print(f"ABORT: selector matched {len(rows)} rows (expected exactly 1).")
            return 2

        r = rows[0]
        print("Target transaction:")
        print(f"  tx_id   = {r['tx_id']}")
        print(f"  symbol  = {r['symbol']}")
        print(f"  type    = {r['type']}")
        print(f"  qty     = {r['quantity']}")
        print(f"  executed_at = {r['executed_at']}")
        print(f"  created_at  = {r['created_at']}")
        print(f"  notes   = {r['notes']}")

        if not args.apply:
            print("\nDry-run: nothing deleted. Re-run with --apply.")
            return 0

        async with eng.begin() as tx_conn:
            res = await tx_conn.execute(
                text("DELETE FROM transactions WHERE id = :tid"),
                {"tid": r["tx_id"]},
            )
            print(f"\nDeleted {res.rowcount} row(s).")
    await eng.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
