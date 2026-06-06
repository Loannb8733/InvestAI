"""Supprime le SELL KAITO doublon du Convert OM<->KAITO du 2025-03-03.

PR #210 a deduplique les ``fiat_<id>`` vs ``convert_<id>`` qui pointent vers
le meme Binance Convert. Mais ce cas a echappe au dedup parce que la jambe
SELL etait prefixee ``fiat_sell_<suffix>`` (et non ``fiat_<id>``), alors
que la jambe Convert etait ``convert_sell_<suffix>``. Meme suffix UUID,
meme date, meme qty.

Suppression de la transaction SELL fantome (qui n'existe pas reellement
chez Binance — c'est juste l'autre cote du Convert).

Dry-run par defaut, --apply pour ecrire. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

SUFFIX = "cbf211ce71f94c93becd3972b60b9048"
SYMBOL = "KAITO"


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
        # Verifier que le doublon existe
        sell = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tid, t.quantity AS q, t.executed_at AS d"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE a.symbol = :sym"
                        "   AND t.transaction_type = 'SELL'"
                        "   AND t.external_id = :ext"
                    ),
                    {"sym": SYMBOL, "ext": f"fiat_sell_{SUFFIX}"},
                )
            )
            .mappings()
            .first()
        )
        if not sell:
            print("Pas de SELL doublon KAITO trouve. Rien a faire (idempotent).")
            return 0

        # Verifier que la jambe CONVERSION_OUT correspondante existe (sinon on ne touche pas)
        conv = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tid, t.quantity AS q"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE a.symbol = :sym"
                        "   AND t.transaction_type = 'CONVERSION_OUT'"
                        "   AND t.external_id = :ext"
                    ),
                    {"sym": SYMBOL, "ext": f"convert_sell_{SUFFIX}"},
                )
            )
            .mappings()
            .first()
        )
        if not conv:
            print("ABORT: pas de CONVERSION_OUT correspondante — refus de supprimer le SELL seul.")
            return 1

        if abs(float(sell["q"]) - float(conv["q"])) > 1e-9:
            print(
                f"ABORT: qty SELL={sell['q']} != qty CONVERSION_OUT={conv['q']}."
                " Le SELL n'est peut-etre pas un doublon."
            )
            return 1

        print(f"SELL doublon: id={sell['tid']}  qty={sell['q']}  date={sell['d']}")
        print(f"CONVERSION_OUT real: id={conv['tid']}  qty={conv['q']}")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply pour supprimer le SELL doublon.")
            return 0

        async with eng.begin() as tx:
            await tx.execute(
                text("DELETE FROM transactions WHERE id = :tid"),
                {"tid": sell["tid"]},
            )
        print(f"\nSupprime. tx_id={sell['tid']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
