"""Backfill assets.current_price depuis asset_price_history.

La colonne ``assets.current_price`` est restee NULL pour 44/50 lignes
en prod parce qu'aucun code ne l'ecrivait. Les calculs marchaient
quand meme parce que l'app fait des ``JOIN asset_price_history`` a la
volee, mais l'endpoint ``/transactions/balance-gaps`` (voucher
detection) lit ``current_price`` directement -> rate les vouchers.

Le job ``_persist_prices_to_db`` (history_cache.py) est maintenant
patche pour mirror le dernier prix dans assets. Ce script fait le
backfill one-shot pour les lignes deja existantes.

Idempotent: ne touche qu'aux lignes ou current_price IS NULL ou
last_price_update est anterieur a la derniere entree
asset_price_history pour ce symbol. Skip CROWDFUNDING.

Dry-run par defaut, --apply pour ecrire.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


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
        # 1) Dry-run preview
        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT a.symbol, a.exchange, a.current_price, a.last_price_update,
                       lph.price_eur AS new_px, lph.price_date AS new_dt
                FROM assets a
                JOIN LATERAL (
                    SELECT price_eur, price_date FROM asset_price_history
                    WHERE symbol = a.symbol
                    ORDER BY price_date DESC LIMIT 1
                ) lph ON true
                WHERE a.asset_type != 'CROWDFUNDING'
                  AND (a.current_price IS NULL
                       OR a.last_price_update IS NULL
                       OR a.last_price_update::date < lph.price_date)
                ORDER BY a.symbol, a.exchange
                """
                    )
                )
            )
            .mappings()
            .all()
        )

        if not rows:
            print("Rien a backfiller. Tous les assets non-crowdfunding sont a jour.")
            return 0

        print(f"{len(rows)} ligne(s) a backfiller:\n")
        for r in rows:
            print(
                f"  {r['symbol']:<10} {(r['exchange'] or '')[:14]:<14} "
                f"old={r['current_price']}  new={r['new_px']}  (price_date={r['new_dt']})"
            )

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        # 2) Apply
        res = await conn.execute(
            text(
                """
            UPDATE assets a
            SET current_price = lph.price_eur,
                last_price_update = NOW()
            FROM (
                SELECT DISTINCT ON (symbol) symbol, price_eur, price_date
                FROM asset_price_history
                ORDER BY symbol, price_date DESC
            ) lph
            WHERE a.symbol = lph.symbol
              AND a.asset_type != 'CROWDFUNDING'
              AND (a.current_price IS NULL
                   OR a.last_price_update IS NULL
                   OR a.last_price_update::date < lph.price_date)
            """
            )
        )
        print(f"\nApplique. {res.rowcount} ligne(s) mises a jour.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
