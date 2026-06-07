"""Repair avg_buy_price + zero out Kraken phantom dust holdings.

Two regressions surfaced after PR #220 + dust snap:

A. Several `assets.avg_buy_price` ended up at 0 even though the
   underlying TRANSFER_IN row carries a price. SQL INSERT in PR #220
   bypassed the API-side `_recalculate_avg_buy_price` helper. Concrete
   prod impact: BTC Tangem stored 0.01518 BTC but PRU = 0 EUR, dragging
   the global PRU down to 17886 EUR (true average ~65000 EUR).

B. After we deleted the zero-out TRANSFER_OUT dust phantoms (PR #220)
   the snap script set `assets.quantity = computed`, putting phantom
   balances back where the exchange actually reports 0. PEPE Kraken
   now shows 109,529 PEPE that the user does not own. Same pattern on
   DOGE/USDG/ETH/SOL Kraken dust.

Fix:
1. SET assets.quantity = 0 for Kraken dust holdings where
   abs(computed) < 5 EUR AND avg_buy_price == 0 (clear phantom from PR #220 over-correction).
2. Recompute avg_buy_price for every non-crowdfunding asset using the
   same formula the API uses:
       sum(qty * price + fee) / sum(qty)
       over (BUY, CONVERSION_IN, TRANSFER_IN) with price > 0
   Skip assets with no qualifying rows (avg stays 0 or current value).

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
        # === STEP A: zero out Kraken/Crypto.com phantom holdings ===
        # Per the user, these positions are really 0 on the exchange.
        # PR #220 over-corrected by snapping stored = computed after
        # deleting the dust TRANSFER_OUT rows; restoring stored = 0.
        PHANTOMS = [
            ("DOGE", "Kraken"),
            ("ETH", "Kraken"),
            ("USDG", "Kraken"),
            ("USDT", "Crypto.com"),
            ("PEPE", "Kraken"),  # user explicitly confirmed: no more PEPE
            ("BTC", "Kraken"),  # dust 0.00002578
            ("SOL", "Kraken"),  # dust 0.0176
            ("PAXG", "Kraken"),  # already had some, but the dust delta is phantom
            ("USDC", "Kraken"),  # 0.3 USDC dust
        ]
        print("=== A. Zero out confirmed phantom holdings ===")
        zeroed = []
        for sym, exch in PHANTOMS:
            row = (
                await conn.execute(
                    text(
                        "SELECT id::text, quantity, avg_buy_price, current_price FROM assets"
                        " WHERE symbol = :s AND exchange = :e LIMIT 1"
                    ),
                    {"s": sym, "e": exch},
                )
            ).first()
            if not row:
                print(f"  {sym} {exch}: asset introuvable, skip")
                continue
            qty = D(row[1])
            px = D(row[3])
            if qty == 0:
                print(f"  {sym} {exch}: deja a 0, skip")
                continue
            val = qty * px
            if val >= Decimal("5") and sym != "PEPE":
                # Safety: never auto-zero if value >= 5 EUR (except PEPE,
                # user explicitly confirmed)
                print(f"  {sym} {exch}: val={float(val):.2f} >= 5 EUR, ABORT zeroing (safety)")
                continue
            # Materialize the OUT (the holding really left the exchange).
            # Compute the signed sum of past transactions to know how much
            # was historically held -- the TRANSFER_OUT must zero that out.
            sig_row = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(CASE"
                        " WHEN transaction_type IN ('BUY','TRANSFER_IN','CONVERSION_IN','AIRDROP','STAKING_REWARD') THEN quantity"
                        " WHEN transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT') THEN -quantity"
                        " ELSE 0 END), 0) AS computed_qty"
                        " FROM transactions WHERE asset_id = :aid"
                    ),
                    {"aid": row[0]},
                )
            ).first()
            historical_qty = D(sig_row[0])
            print(
                f"  ZERO {sym:<8} {exch:<12} qty={float(qty):.8f} -> 0  "
                f"(val was {float(val):.2f} EUR, historical computed_qty={float(historical_qty):.8f})"
            )
            if args.apply:
                await conn.execute(
                    text("UPDATE assets SET quantity = 0 WHERE id = :aid"),
                    {"aid": row[0]},
                )
                if historical_qty > 0:
                    # Materialise OUT to zero the computed signed sum
                    await conn.execute(
                        text(
                            "INSERT INTO transactions"
                            " (id, asset_id, transaction_type, quantity, price, fee,"
                            "  currency, executed_at, external_id, notes, created_at)"
                            " VALUES (gen_random_uuid(), :aid, 'TRANSFER_OUT', :qty,"
                            "         0, 0, 'EUR', NOW(), :ext, :notes, NOW())"
                        ),
                        {
                            "aid": row[0],
                            "qty": historical_qty,
                            "ext": f"manual_phantom_out_{sym}_{exch}_20260607",
                            "notes": (
                                f"Phantom holding zeroed 2026-06-07: "
                                f"{exch} reports 0 {sym}, snapshot history "
                                f"showed {historical_qty} accumulated. "
                                f"User confirms no longer owns this position."
                            ),
                        },
                    )
            zeroed.append(f"{sym}/{exch}")
        print(f"  -> {len(zeroed)} zeroed")

        # === STEP B: recompute avg_buy_price for all assets ===
        print(f"\n=== B. Recompute avg_buy_price across non-crowdfunding ===")
        # SUM(qty*price + fee) / SUM(qty) over (BUY, CONV_IN, TRANSFER_IN), price > 0
        recomputed = (
            (
                await conn.execute(
                    text(
                        """
                SELECT a.id::text AS aid, a.symbol, a.exchange, a.avg_buy_price AS old,
                       CASE
                           WHEN SUM(CASE WHEN t.price > 0 THEN t.quantity ELSE 0 END) > 0
                           THEN SUM(CASE WHEN t.price > 0 THEN t.quantity * t.price + COALESCE(t.fee,0) ELSE 0 END)
                                / SUM(CASE WHEN t.price > 0 THEN t.quantity ELSE 0 END)
                           ELSE NULL
                       END AS new_avg
                FROM assets a
                LEFT JOIN transactions t ON t.asset_id = a.id
                    AND t.transaction_type IN ('BUY', 'CONVERSION_IN', 'TRANSFER_IN')
                WHERE a.asset_type != 'CROWDFUNDING'
                GROUP BY a.id, a.symbol, a.exchange, a.avg_buy_price
                HAVING ABS(COALESCE(a.avg_buy_price, 0) - COALESCE(
                    CASE
                        WHEN SUM(CASE WHEN t.price > 0 THEN t.quantity ELSE 0 END) > 0
                        THEN SUM(CASE WHEN t.price > 0 THEN t.quantity * t.price + COALESCE(t.fee,0) ELSE 0 END)
                                / SUM(CASE WHEN t.price > 0 THEN t.quantity ELSE 0 END)
                        ELSE 0
                    END, 0)) > 0.01
                ORDER BY a.symbol, a.exchange
                """
                    )
                )
            )
            .mappings()
            .all()
        )

        for r in recomputed:
            new_avg = r["new_avg"]
            if new_avg is None:
                continue
            print(
                f"  {r['symbol']:<8} {r['exchange']:<12} avg {float(r['old'] or 0):>14.4f} -> {float(new_avg):>14.4f}"
            )
            if args.apply:
                await conn.execute(
                    text("UPDATE assets SET avg_buy_price = :avg WHERE id = :aid"),
                    {"avg": new_avg, "aid": r["aid"]},
                )
        print(f"  -> {len(recomputed)} avg_buy_price updated")

    if not args.apply:
        print("\nDry-run. Re-run avec --apply.")
    else:
        print("\nApplique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
