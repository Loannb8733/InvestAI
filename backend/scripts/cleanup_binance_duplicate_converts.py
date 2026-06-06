"""Remove duplicate Binance Convert transactions (wave 7 follow-up).

Background
==========
Two functions in ``app/services/exchanges/binance.py`` used to read the SAME
endpoint (``/sapi/v1/convert/tradeFlow``) and produce two distinct rows per
conversion:

- ``get_fiat_orders`` emitted SELL/BUY with ``external_id = fiat_<orderId>``
  (it treated stablecoins as fiat).
- ``get_crypto_conversions`` emitted CONVERSION_OUT/CONVERSION_IN with
  ``external_id = convert_sell_<orderId>`` / ``convert_buy_<orderId>``.

The repo-side fix (PR following #209) limits ``get_fiat_orders`` to true fiat
so future syncs no longer duplicate. This script handles the **legacy rows
already persisted in prod** by removing the ``fiat_<orderId>`` row whenever a
sibling ``convert_*_<orderId>`` row exists for the same Binance ``orderId``.

Safety
======
- Default mode is **dry-run**. Nothing is written unless you pass ``--apply``.
- Only matches rows whose external_id starts with ``fiat_`` and whose suffix
  appears in a ``convert_sell_`` or ``convert_buy_`` sibling on Binance.
- Always prints the count and a small sample before / instead of deleting.
- Refuses to delete more than ``--max`` rows (default 500) unless you bump it.

Usage
=====
::

    DATABASE_URL='postgresql://...' python -m scripts.cleanup_binance_duplicate_converts
    DATABASE_URL='postgresql://...' python -m scripts.cleanup_binance_duplicate_converts --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    return url


# Matches the ``fiat_<orderId>`` rows whose orderId is also referenced by a
# convert_sell_/convert_buy_ sibling. The substring-match version (RIGHT/LIKE)
# handles the historical case where the prefix length isn't perfectly aligned.
SELECT_DUPLICATES = """
    WITH fiat_rows AS (
        SELECT id, external_id, executed_at, quantity, transaction_type::text AS ttype, asset_id
        FROM transactions
        WHERE exchange = 'Binance' AND external_id LIKE 'fiat_%'
    ),
    convert_suffixes AS (
        SELECT DISTINCT
            CASE
                WHEN external_id LIKE 'convert_sell_%' THEN SUBSTR(external_id, LENGTH('convert_sell_') + 1)
                WHEN external_id LIKE 'convert_buy_%'  THEN SUBSTR(external_id, LENGTH('convert_buy_')  + 1)
            END AS suffix
        FROM transactions
        WHERE exchange = 'Binance' AND (external_id LIKE 'convert_sell_%' OR external_id LIKE 'convert_buy_%')
    )
    SELECT f.id, f.external_id, f.executed_at, f.quantity, f.ttype, f.asset_id, c.suffix
    FROM fiat_rows f
    JOIN convert_suffixes c ON f.external_id LIKE ('fiat_' || c.suffix || '%')
    ORDER BY f.executed_at NULLS LAST
"""


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    p.add_argument("--max", type=int, default=500, help="refuse to delete more than this (safety)")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    async with eng.connect() as conn:
        rows = (await conn.execute(text(SELECT_DUPLICATES))).mappings().all()

        if not rows:
            print("Nothing to delete — no duplicate fiat_* / convert_*_* siblings on Binance.")
            await eng.dispose()
            return 0

        print(f"Matched {len(rows)} duplicate row(s).\n")
        for r in rows[:15]:
            ts = r["executed_at"].strftime("%Y-%m-%d %H:%M") if r["executed_at"] else "—"
            print(
                f"  id={str(r['id'])[:8]} {ts}  {r['ttype']:14}  qty={float(r['quantity']):>14.6f}  ext={r['external_id'][:40]}"
            )
        if len(rows) > 15:
            print(f"  … and {len(rows) - 15} more")

        if not args.apply:
            print("\nDry-run: nothing deleted. Re-run with --apply to delete.")
            await eng.dispose()
            return 0

        if len(rows) > args.max:
            print(
                f"\nABORT: matched {len(rows)} rows, above --max={args.max}. Re-run with a higher --max if you trust the diff."
            )
            await eng.dispose()
            return 1

        ids = [r["id"] for r in rows]
        async with eng.begin() as tx_conn:
            res = await tx_conn.execute(
                text("DELETE FROM transactions WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
            print(f"\nDeleted {res.rowcount} row(s). Commit done.")
        await eng.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
