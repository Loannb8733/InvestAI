"""Corrige le prix aberrant d'un Convert USDT du 2026-05-05.

La transaction ``convert_sell_00bc9edbd4634b4ca3ec04a8396`` a un
``price = 240154.21 EUR/USDT`` au lieu de ~0.85 EUR/USDT, ce qui injecte
un cost basis fictif de 3.4M EUR dans le portefeuille (visible dans
l'audit P&L multi-crypto).

Cause probable : ratio inverse lors du parsing Binance Convert. Le bon
prix de marche USDT->EUR est ~ ``fx_daily_rates.rate(USD,EUR,2026-05-05)``.

Dry-run par defaut, --apply pour ecrire. Idempotent (skip si price < 100).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXT = "convert_sell_00bc9edbd4634b4ca3ec04a8396f03f2"
ABERRANT_THRESHOLD = Decimal("100")  # USDT @ 100 EUR == clairement aberrant


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
    async with eng.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tid, t.quantity AS q, t.price AS p,"
                        " t.executed_at AS d"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE a.symbol = 'USDT' AND t.external_id = :ext"
                    ),
                    {"ext": EXT},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            print(f"Transaction {EXT} introuvable. Rien a faire.")
            return 0

        cur_price = D(row["p"])
        if cur_price < ABERRANT_THRESHOLD:
            print(f"Prix actuel {cur_price} < seuil aberrant — fix deja applique. Skip.")
            return 0

        day = row["d"].date()
        fx_row = (
            await conn.execute(
                text(
                    "SELECT rate FROM fx_daily_rates"
                    " WHERE base_currency='USD' AND quote_currency='EUR'"
                    "   AND rate_date <= :d ORDER BY rate_date DESC LIMIT 1"
                ),
                {"d": day},
            )
        ).first()
        if not fx_row:
            print("Pas de fx USD->EUR disponible.")
            return 1
        new_price = D(fx_row[0])

        qty = D(row["q"])
        print(f"USDT tx_id={row['tid']}  qty={qty}  date={day}")
        print(f"Prix actuel aberrant: {cur_price} EUR/USDT")
        print(f"USD->EUR @ {day}: {new_price}")
        print(f"=> nouveau cost EUR = qty * new_price = {float(qty * new_price):.4f}")
        print(f"   (ancien cost: {float(qty * cur_price):,.2f} — bug catastrophique)")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        async with eng.begin() as tx:
            await tx.execute(
                text("UPDATE transactions SET price = :px WHERE id = :tid"),
                {"px": new_price, "tid": row["tid"]},
            )
        print(f"\nApplique. tx_id={row['tid']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
