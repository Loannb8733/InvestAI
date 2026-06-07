"""Correct the BTC Tangem TRANSFER_IN with the real received amount + fee.

Follow-up to PR #220 which paired the Binance OUT with a Tangem IN of
0.01384369 BTC. Per the user's Binance withdrawal screen, the real
breakdown is:

* Montant envoye    : 0.01384369 BTC (Binance OUT, unchanged)
* Montant a recevoir: 0.01382869 BTC (Tangem IN, was wrong)
* Frais reseau      :  0.00001500 BTC (lost to miners)

Fix:
1. UPDATE the Tangem TRANSFER_IN quantity 0.01384369 -> 0.01382869
2. SET fee = 0.00001500 on the Tangem IN (track the network fee)
3. UPDATE Tangem BTC assets.quantity: subtract 0.00001500 BTC
   (the fee is a real loss, not a holding).

Idempotent (skip if Tangem IN qty already == 0.01382869).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BTC_OUT_EXT = "Binance_zero_BTC_1780868799"
TARGET_TANGEM_QTY = Decimal("0.01382869")
NETWORK_FEE_BTC = Decimal("0.00001500")
OLD_TANGEM_QTY = Decimal("0.01384369")  # what PR #220 wrote


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
        # Find the Tangem IN created by PR #220
        in_row = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tid, t.quantity, t.fee, a.id::text AS aid"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE a.symbol = 'BTC' AND a.exchange = 'Tangem'"
                        "   AND t.external_id = :e"
                    ),
                    {"e": f"Tangem_in_paired_{BTC_OUT_EXT}"},
                )
            )
            .mappings()
            .first()
        )
        if not in_row:
            print("Tangem IN introuvable (PR #220 pas applique ?). Abort.")
            return 1

        cur_qty = Decimal(str(in_row["quantity"]))
        if abs(cur_qty - TARGET_TANGEM_QTY) < Decimal("1e-8"):
            print(f"Tangem IN deja a {TARGET_TANGEM_QTY}. Idempotent skip.")
            return 0

        print(
            f"Tangem IN  tid={in_row['tid'][:8]}  qty {cur_qty} -> {TARGET_TANGEM_QTY}"
            f"  fee 0 -> {NETWORK_FEE_BTC} BTC"
        )
        print(f"Tangem assets.quantity correction: -{NETWORK_FEE_BTC} BTC")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        # 1) Update Tangem IN qty + fee
        await conn.execute(
            text("UPDATE transactions" " SET quantity = :q, fee = :f, fee_currency = 'BTC'" " WHERE id = :tid"),
            {"q": TARGET_TANGEM_QTY, "f": NETWORK_FEE_BTC, "tid": in_row["tid"]},
        )
        # 2) Update Tangem BTC stored: remove the 0.00001500 fee delta
        await conn.execute(
            text("UPDATE assets SET quantity = quantity - :delta" " WHERE id = :aid"),
            {"delta": NETWORK_FEE_BTC, "aid": in_row["aid"]},
        )
        print("Applique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
