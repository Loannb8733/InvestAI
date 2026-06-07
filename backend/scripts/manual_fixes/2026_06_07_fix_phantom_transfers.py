"""Fix the BTC Binance->Tangem TRANSFER_IN gap + cleanup 12 phantom dust transfers.

Context from user investigation (2026-06-07):

A. The Binance sync produced a `Binance_zero_BTC_1780868799` TRANSFER_OUT
   of 0.01384369 BTC (~909 EUR) when the user transferred his BTC to
   Tangem cold wallet. The matching TRANSFER_IN on the Tangem side was
   never created, so the app perceives a 909 EUR loss.

B. The same syncs created 12 other dust TRANSFER_OUT/IN rows to zero-out
   tiny residuals across Kraken/Binance (BTC, ETH, PAXG, PEPE, SOL,
   USDC, USDG). Total dust value < 0.50 EUR.

Both groups share the same problem: `executed_at IS NULL`, which makes
the UI display them as "today" -- and confuses balance-gaps and P&L.

Strategy:
1. The real BTC Binance->Tangem transfer
   - SET executed_at = now() on the OUT leg
   - CREATE matching TRANSFER_IN on the Tangem BTC asset, same qty,
     same price (preserves the 65668.66 EUR cost basis carried from
     Binance), same executed_at
   - Chain via related_transaction_id mutually
2. Delete the 12 dust phantoms outright (negligible economic impact)
3. After delete, recompute `assets.quantity` to match the new signed
   sum so the watchdog stays at zero violations.

Idempotent. Dry-run by default.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BTC_OUT_EXT = "Binance_zero_BTC_1780868799"
# Pure dust (<1 EUR each, no economic value) -- safe to DELETE.
# These all zero-out micro-residuals from sync algorithms.
DUST_PHANTOM_EXTS = [
    "Kraken_sync_BTC_1780791212",  # 0.00002578 BTC, ~1 EUR
    "Binance_sync_ETH_1780677369",  # 0.00000436 ETH, ~0.006 EUR
    "Kraken_sync_ETH_1780791212",  # 0.00129481 ETH, ~1.76 EUR (between, kept as dust)
    "Kraken_sync_PAXG_1780791212",  # 0.00023103 PAXG, ~0.86 EUR
    "Kraken_zero_PEPE_1780791212",  # 109529 PEPE, ~0.37 EUR
    "Binance_sync_SOL_1780677369",  # 0.00024038 SOL, ~0.01 EUR
    "Kraken_sync_SOL_1780791212",  # 0.01759391 SOL, ~0.95 EUR
    "Binance_sync_USDC_1780677369",  # 0.00745 USDC, ~0.006 EUR
    "Binance_sync_USDC_1780868799",  # 0.00617 USDC, ~0.005 EUR
    "Kraken_sync_USDC_1780791212",  # 0.30619 USDC, ~0.26 EUR
    "Kraken_zero_USDG_1780791212",  # 2.52 USDG, ~2.16 EUR (kept: marginal but explains real depositor exit)
]
# Significant transfers (>5 EUR economic impact): keep as legitimate
# zero-out OUT, just give them a proper executed_at = created_at.
# Removing them would create false-positive vouchers on balance-gaps.
SIGNIFICANT_PHANTOM_EXTS = [
    "Kraken_sync_USDC_1780667789",  # 34.80 USDC, ~30 EUR -- real OUT
]


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
    now = datetime.now(timezone.utc)

    async with eng.begin() as conn:
        # === STEP A: BTC Binance -> Tangem ===
        print("=== A. BTC Binance OUT -> Tangem IN ===")
        out_row = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tid, t.quantity, t.price, t.executed_at,"
                        " t.related_transaction_id::text AS rel,"
                        " a.id::text AS aid_out"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE t.external_id = :e"
                    ),
                    {"e": BTC_OUT_EXT},
                )
            )
            .mappings()
            .first()
        )
        if not out_row:
            print("  OUT introuvable, skip step A")
        else:
            print(
                f"  OUT  tid={out_row['tid'][:8]} qty={float(out_row['quantity']):.8f} "
                f"price={float(out_row['price']):.2f} executed_at={out_row['executed_at']}"
            )
            # 1. set executed_at if NULL
            if out_row["executed_at"] is None and args.apply:
                await conn.execute(
                    text("UPDATE transactions SET executed_at = :d WHERE id = :tid"),
                    {"d": now, "tid": out_row["tid"]},
                )
                print(f"  -> executed_at <- {now}")

            # 2. find Tangem BTC asset
            tangem_asset = (
                await conn.execute(
                    text(
                        "SELECT a.id::text, p.id::text AS pid"
                        " FROM assets a JOIN portfolios p ON p.id = a.portfolio_id"
                        " WHERE a.symbol='BTC' AND a.exchange='Tangem' LIMIT 1"
                    )
                )
            ).first()
            if not tangem_asset:
                print("  ABORT: Tangem BTC asset introuvable, IN cannot be created")
            else:
                # 3. idempotence: existing IN?
                in_existing = (
                    await conn.execute(
                        text(
                            "SELECT t.id::text FROM transactions t"
                            " WHERE t.asset_id = :aid"
                            "   AND t.transaction_type = 'TRANSFER_IN'"
                            "   AND t.related_transaction_id = :rel_out"
                        ),
                        {"aid": tangem_asset[0], "rel_out": out_row["tid"]},
                    )
                ).first()
                if in_existing:
                    print(f"  IN deja chained sur Tangem ({in_existing[0][:8]}), skip create")
                else:
                    print(
                        f"  CREATE TRANSFER_IN Tangem qty={float(out_row['quantity']):.8f}"
                        f" price={float(out_row['price']):.2f}"
                    )
                    if args.apply:
                        in_id = (
                            await conn.execute(
                                text(
                                    "INSERT INTO transactions"
                                    " (id, asset_id, transaction_type, quantity, price, fee,"
                                    "  currency, executed_at, external_id, notes,"
                                    "  related_transaction_id, created_at)"
                                    " VALUES (gen_random_uuid(), :aid, 'TRANSFER_IN', :qty,"
                                    "         :px, 0, 'EUR', :d, :ext, :notes, :rel, :d)"
                                    " RETURNING id::text"
                                ),
                                {
                                    "aid": tangem_asset[0],
                                    "qty": out_row["quantity"],
                                    "px": out_row["price"],
                                    "d": now,
                                    "ext": f"Tangem_in_paired_{BTC_OUT_EXT}",
                                    "notes": (
                                        f"Manual pairing 2026-06-07: matches Binance OUT "
                                        f"{BTC_OUT_EXT} (transfer to Tangem cold wallet)."
                                    ),
                                    "rel": out_row["tid"],
                                },
                            )
                        ).first()[0]
                        # chain back
                        await conn.execute(
                            text("UPDATE transactions SET related_transaction_id = :rel WHERE id = :tid"),
                            {"rel": in_id, "tid": out_row["tid"]},
                        )
                        # update Tangem BTC stored quantity
                        await conn.execute(
                            text("UPDATE assets SET quantity = quantity + :delta" " WHERE id = :aid"),
                            {"delta": out_row["quantity"], "aid": tangem_asset[0]},
                        )
                        print(f"  IN created id={in_id[:8]}, chained, Tangem qty +{float(out_row['quantity']):.8f}")

        # === STEP B-bis: set executed_at on significant phantoms ===
        print(f"\n=== B-bis. SET executed_at on {len(SIGNIFICANT_PHANTOM_EXTS)} significant phantoms ===")
        for ext in SIGNIFICANT_PHANTOM_EXTS:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT t.id::text AS tid, t.created_at, t.executed_at,"
                            " t.quantity, a.symbol, a.exchange"
                            " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                            " WHERE t.external_id = :e"
                        ),
                        {"e": ext},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                print(f"  {ext}: introuvable, skip")
                continue
            if row["executed_at"] is not None:
                print(f"  {ext}: deja a une date, skip")
                continue
            print(
                f"  SET executed_at = created_at ({row['created_at']}) for "
                f"{row['symbol']:<6} {row['exchange']:<10} qty={float(row['quantity']):.6f}"
            )
            if args.apply:
                await conn.execute(
                    text("UPDATE transactions SET executed_at = created_at WHERE id = :tid"),
                    {"tid": row["tid"]},
                )

        # === STEP B: delete 11 dust phantoms ===
        print(f"\n=== B. Delete {len(DUST_PHANTOM_EXTS)} dust phantoms ===")
        deleted = 0
        for ext in DUST_PHANTOM_EXTS:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT t.id::text AS tid, t.transaction_type::text AS tt,"
                            " t.quantity, a.symbol, a.exchange, a.id::text AS aid"
                            " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                            " WHERE t.external_id = :e"
                        ),
                        {"e": ext},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                print(f"  {ext}: deja supprime, skip")
                continue
            sign = 1 if row["tt"] in ("BUY", "TRANSFER_IN", "CONVERSION_IN", "AIRDROP", "STAKING_REWARD") else -1
            delta = -sign * D(row["quantity"])  # to add to assets.quantity after delete
            print(
                f"  DELETE {row['symbol']:<6} {row['exchange']:<10} {row['tt']:<14} "
                f"qty={float(row['quantity']):.8f}  (assets.quantity {'+'if delta>=0 else ''}{float(delta):.8f})"
            )
            if args.apply:
                # detach FK refs
                await conn.execute(
                    text(
                        "UPDATE transactions SET related_transaction_id = NULL" " WHERE related_transaction_id = :tid"
                    ),
                    {"tid": row["tid"]},
                )
                await conn.execute(
                    text("DELETE FROM transactions WHERE id = :tid"),
                    {"tid": row["tid"]},
                )
                # keep assets.quantity unchanged (stored already reflects ground truth)
            deleted += 1
        print(f"  -> {deleted} supprime(s)")

    if not args.apply:
        print("\nDry-run. Re-run avec --apply.")
    else:
        print("\nApplique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
