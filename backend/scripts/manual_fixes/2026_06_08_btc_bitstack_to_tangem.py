"""Track the missing Bitstack -> Tangem BTC transfer of 2026-06-07 09:48 AM.

User confirmed via Tangem mobile wallet that his real BTC balance there
is 0.0172483 BTC, while the DB only knows about 0.01520307 BTC (four
TRANSFER_IN rows). The missing 0.00207101 BTC matches exactly the
Bitstack BTC balance (0.00207101) that the DB still thinks he holds.

Conclusion: he transferred his Bitstack holdings to Tangem on
2026-06-07 around 09:48 AM (visible in the Tangem app history).

Fix:
1. Create TRANSFER_OUT 0.00207101 BTC on Bitstack
2. Create TRANSFER_IN 0.00207101 BTC on Tangem with the Bitstack
   avg_buy_price (78561.88 EUR/BTC) so the cost basis migrates intact
3. Chain via related_transaction_id
4. UPDATE assets quantity:
   - Bitstack BTC: 0.00207101 -> 0
   - Tangem BTC: 0.01520307 -> 0.0172483 (= signed sum after the new IN)
5. Recompute Tangem BTC avg_buy_price (weighted avg of all IN layers)
6. Bitstack avg_buy_price stays as the historical PRA (qty=0 doesn't
   need it but kept for traceability).

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

TRANSFER_QTY = Decimal("0.00207101")
BITSTACK_AVG = Decimal("78561.88645249")  # Bitstack's avg_buy_price
EXEC_TIME = datetime(2026, 6, 7, 9, 48, 0, tzinfo=timezone.utc)
EXT_OUT = "Bitstack_out_to_tangem_2026_06_07_09_48"
EXT_IN = "Tangem_in_from_bitstack_2026_06_07_09_48"


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
        # 1. Fetch asset IDs
        bitstack = (
            await conn.execute(
                text(
                    "SELECT id::text, quantity, avg_buy_price FROM assets"
                    " WHERE symbol = 'BTC' AND exchange = 'Bitstack'"
                )
            )
        ).first()
        tangem = (
            await conn.execute(
                text(
                    "SELECT id::text, quantity, avg_buy_price FROM assets"
                    " WHERE symbol = 'BTC' AND exchange = 'Tangem'"
                )
            )
        ).first()
        if not bitstack or not tangem:
            print("Bitstack ou Tangem BTC asset introuvable. Abort.")
            return 1

        bitstack_aid = bitstack[0]
        tangem_aid = tangem[0]

        print(f"Bitstack BTC: id={bitstack_aid[:8]}  qty={bitstack[1]}  avg={bitstack[2]}")
        print(f"Tangem BTC  : id={tangem_aid[:8]}  qty={tangem[1]}  avg={tangem[2]}")

        # Idempotence
        existing_out = (
            await conn.execute(
                text("SELECT id::text FROM transactions WHERE external_id = :e"),
                {"e": EXT_OUT},
            )
        ).first()
        if existing_out:
            print(f"TRANSFER_OUT deja present ({existing_out[0][:8]}). Idempotent skip.")
            return 0

        print()
        print(f"Will CREATE TRANSFER_OUT Bitstack {TRANSFER_QTY} BTC @ {BITSTACK_AVG}")
        print(f"Will CREATE TRANSFER_IN  Tangem  {TRANSFER_QTY} BTC @ {BITSTACK_AVG}")
        print(f"Will UPDATE Bitstack BTC qty 0.00207101 -> 0")
        print(f"Will UPDATE Tangem BTC   qty 0.01520307 -> 0.01727408")
        print(f"Will RECOMPUTE Tangem avg_buy_price from all IN layers")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        # 2. Create TRANSFER_OUT on Bitstack
        out_id = (
            await conn.execute(
                text(
                    "INSERT INTO transactions"
                    " (id, asset_id, transaction_type, quantity, price, fee,"
                    "  currency, executed_at, external_id, notes, created_at)"
                    " VALUES (gen_random_uuid(), :aid, 'TRANSFER_OUT', :qty, :px,"
                    "         0, 'EUR', :d, :ext, :notes, :d)"
                    " RETURNING id::text"
                ),
                {
                    "aid": bitstack_aid,
                    "qty": TRANSFER_QTY,
                    "px": BITSTACK_AVG,
                    "d": EXEC_TIME,
                    "ext": EXT_OUT,
                    "notes": (
                        "Manual tracking 2026-06-08: Bitstack BTC transferred to Tangem"
                        " on 2026-06-07 09:48 AM (confirmed via Tangem mobile wallet)."
                    ),
                },
            )
        ).first()[0]

        # 3. Create TRANSFER_IN on Tangem with cost basis preserved
        in_id = (
            await conn.execute(
                text(
                    "INSERT INTO transactions"
                    " (id, asset_id, transaction_type, quantity, price, fee,"
                    "  currency, executed_at, external_id, notes,"
                    "  related_transaction_id, created_at)"
                    " VALUES (gen_random_uuid(), :aid, 'TRANSFER_IN', :qty, :px,"
                    "         0, 'EUR', :d, :ext, :notes, :rel, :d)"
                    " RETURNING id::text"
                ),
                {
                    "aid": tangem_aid,
                    "qty": TRANSFER_QTY,
                    "px": BITSTACK_AVG,
                    "d": EXEC_TIME,
                    "ext": EXT_IN,
                    "notes": (
                        "Manual tracking 2026-06-08: BTC received from Bitstack"
                        " on 2026-06-07 09:48 AM. Cost basis 78561.89 EUR/BTC"
                        " preserved from source exchange."
                    ),
                    "rel": out_id,
                },
            )
        ).first()[0]

        # 4. Chain back
        await conn.execute(
            text("UPDATE transactions SET related_transaction_id = :rel WHERE id = :tid"),
            {"rel": in_id, "tid": out_id},
        )

        # 5. Set Bitstack BTC quantity to 0
        await conn.execute(
            text("UPDATE assets SET quantity = 0 WHERE id = :aid"),
            {"aid": bitstack_aid},
        )

        # 6. Update Tangem BTC: add 0.00207101 + recompute avg_buy_price
        await conn.execute(
            text(
                "UPDATE assets a"
                " SET quantity = sub.computed_qty,"
                "     avg_buy_price = COALESCE(sub.new_avg, a.avg_buy_price)"
                " FROM ("
                "   SELECT a2.id AS aid,"
                "     COALESCE(SUM(CASE"
                "         WHEN t.transaction_type IN ('BUY','TRANSFER_IN','CONVERSION_IN','AIRDROP','STAKING_REWARD')"
                "             THEN t.quantity"
                "         WHEN t.transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT')"
                "             THEN -t.quantity ELSE 0 END), 0) AS computed_qty,"
                "     COALESCE("
                "         SUM(CASE WHEN t.transaction_type IN ('BUY','CONVERSION_IN','TRANSFER_IN') AND t.price > 0"
                "                  THEN t.quantity * t.price + COALESCE(t.fee, 0) ELSE 0 END)"
                "         / NULLIF(SUM(CASE WHEN t.transaction_type IN ('BUY','CONVERSION_IN','TRANSFER_IN') AND t.price > 0"
                "                          THEN t.quantity ELSE 0 END), 0)"
                "       , NULL) AS new_avg"
                "   FROM assets a2 LEFT JOIN transactions t ON t.asset_id = a2.id"
                "   WHERE a2.id = :aid"
                "   GROUP BY a2.id"
                " ) sub"
                " WHERE a.id = sub.aid"
            ),
            {"aid": tangem_aid},
        )

        # Verification print
        final = (
            await conn.execute(
                text("SELECT quantity, avg_buy_price FROM assets WHERE id = :aid"),
                {"aid": tangem_aid},
            )
        ).first()
        print(f"\nApplique. Tangem BTC final qty={final[0]}  avg={final[1]}")
        print(f"Out tid={out_id[:8]}  In tid={in_id[:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
