"""Restore Tangem (cold wallet) holdings from transaction signed sum.

Diagnostic of 2026-06-07: the user reported a perceived BTC P&L of -69 EUR
on the dashboard while the true P&L (per market price + cost basis) is
-219 EUR. Root cause: Tangem BTC `assets.quantity` was 0 EUR despite four
real TRANSFER_IN rows summing to 0.01520307 BTC.

Most likely cause (suspect chain):
* `app/tasks/cleanup.py` runs `is_cold_or_unassigned` heal on Tangem
  assets after every detected inconsistency.
* If the cleanup loop runs while a sync is mid-flight (mirror TRANSFER_IN
  not yet flushed), `calc_qty` reads as 0 and heals the cold wallet to 0.
* The sync continues, creates the mirror TRANSFER_IN, but the
  asset.quantity never gets re-incremented.

This script reconciles `assets.quantity` and `avg_buy_price` for every
Tangem asset based on the actual transaction history. Safe to re-run
any time the dashboard P&L looks off.

Idempotent. Dry-run by default.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

COLD_WALLET = "Tangem"


def D(v):
    return Decimal(str(v or 0))


def _database_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    eng = create_async_engine(_database_url(), echo=False)

    async with eng.begin() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT a.id::text AS aid, a.symbol, a.quantity AS stored,
                       a.avg_buy_price AS old_avg,
                       COALESCE(SUM(CASE
                           WHEN t.transaction_type IN ('BUY','TRANSFER_IN','CONVERSION_IN','AIRDROP','STAKING_REWARD')
                               THEN t.quantity
                           WHEN t.transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT')
                               THEN -t.quantity ELSE 0 END), 0) AS computed,
                       COALESCE(
                         SUM(CASE WHEN t.transaction_type IN ('BUY','CONVERSION_IN','TRANSFER_IN') AND t.price > 0
                                  THEN t.quantity * t.price + COALESCE(t.fee, 0)
                                  ELSE 0 END)
                         / NULLIF(SUM(CASE WHEN t.transaction_type IN ('BUY','CONVERSION_IN','TRANSFER_IN') AND t.price > 0
                                          THEN t.quantity ELSE 0 END), 0)
                       , 0) AS new_avg
                FROM assets a
                LEFT JOIN transactions t ON t.asset_id = a.id
                WHERE a.exchange = :ex
                  AND a.asset_type != 'CROWDFUNDING'
                GROUP BY a.id, a.symbol, a.quantity, a.avg_buy_price
                ORDER BY a.symbol
                """
                    ),
                    {"ex": COLD_WALLET},
                )
            )
            .mappings()
            .all()
        )

        print(f"=== {COLD_WALLET} cold wallet reconciliation ===")
        fixes = 0
        for r in rows:
            stored = D(r["stored"])
            comp = D(r["computed"])
            old_avg = D(r["old_avg"])
            new_avg = D(r["new_avg"])
            qty_diff = comp - stored
            avg_diff = new_avg - old_avg
            needs_qty = abs(qty_diff) > Decimal("1e-8")
            needs_avg = abs(avg_diff) > Decimal("0.01") and new_avg > 0
            if not needs_qty and not needs_avg:
                print(f"  {r['symbol']:<8} OK (qty={float(stored)})")
                continue
            print(
                f"  {r['symbol']:<8} stored={float(stored):.8f} -> {float(comp):.8f}  "
                f"avg_buy={float(old_avg):.2f} -> {float(new_avg):.2f}"
            )
            if args.apply:
                if needs_qty:
                    await conn.execute(
                        text("UPDATE assets SET quantity = :q WHERE id = :a"),
                        {"q": comp, "a": r["aid"]},
                    )
                if needs_avg:
                    await conn.execute(
                        text("UPDATE assets SET avg_buy_price = :p WHERE id = :a"),
                        {"p": new_avg, "a": r["aid"]},
                    )
            fixes += 1
        print(f"\n{fixes} asset(s) " + ("fixed." if args.apply else "to fix (dry-run)."))
    if not args.apply:
        print("Re-run avec --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
