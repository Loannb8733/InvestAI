"""Materialise la perte de 25.21 USDT sortis de Binance hors-traçage.

Apres correction des doublons (PR #215) il reste un delta USDT Binance:

* stored = 0 USDT (verite Binance, confirmee par l'utilisateur)
* computed = 25.21 USDT (sur la base des transactions importees)

L'utilisateur a verifie son Binance Transaction History et confirme qu'il
n'y a aucune trace de ces 25 USDT (probablement Binance Pay/Card/Gift —
non visibles dans l'historique standard). Plutot que de falsifier une
transaction IN reelle (BUY fiat 41.95 USDT en 2025-03 ou TRANSFER_IN
148.52 USDT en 2026-05), on materialise une OUT correctrice avec note
explicite.

Idempotent (skip si already applied). Dry-run par defaut.
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

EXT = "manual_adjust_usdt_orphan_2026_06_07"
QTY = Decimal("25.21194800")
NOTES = (
    "Manual adjustment 2026-06-07: 25.21 USDT lost via untracked Binance"
    " operation (Pay/Card/Gift) — Binance free balance confirmed = 0 USDT."
)


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
        # Asset id USDT Binance
        asset_row = (
            await conn.execute(
                text("SELECT id::text FROM assets" " WHERE symbol = 'USDT' AND exchange = 'Binance' LIMIT 1")
            )
        ).first()
        if not asset_row:
            print("Asset USDT Binance introuvable. Abort.")
            return 1
        asset_id = asset_row[0]

        # Idempotence
        existing = (
            await conn.execute(
                text("SELECT id::text FROM transactions WHERE external_id = :e"),
                {"e": EXT},
            )
        ).first()
        if existing:
            print(f"Adjustment deja present ({existing[0][:8]}) — skip.")
            return 0

        # USD->EUR du jour pour valoriser la perte
        fx = (
            await conn.execute(
                text(
                    "SELECT rate FROM fx_daily_rates"
                    " WHERE base_currency='USD' AND quote_currency='EUR'"
                    " ORDER BY rate_date DESC LIMIT 1"
                )
            )
        ).first()
        usd_eur = Decimal(str(fx[0])) if fx else Decimal("0.86")

        now = datetime.now(timezone.utc)
        print(f"USDT TRANSFER_OUT qty={QTY}  price={usd_eur} EUR/USDT")
        print(f"  total perte materialisee = {float(QTY * usd_eur):.2f} EUR")
        print(f"  ext={EXT}")
        print(f"  notes={NOTES}")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        await conn.execute(
            text(
                "INSERT INTO transactions"
                " (id, asset_id, transaction_type, quantity, price, fee,"
                "  currency, executed_at, external_id, notes, created_at)"
                " VALUES (gen_random_uuid(), :aid, 'TRANSFER_OUT', :qty, :px,"
                "         0, 'EUR', :now, :ext, :notes, :now)"
            ),
            {
                "aid": asset_id,
                "qty": QTY,
                "px": usd_eur,
                "now": now,
                "ext": EXT,
                "notes": NOTES,
            },
        )
        print("\nApplique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
