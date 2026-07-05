"""Read-only: retrouve les événements SOURCES des mirrors suspects vers Tangem.

Pour chaque mirror TRANSFER_IN @Tangem (ETH/SOL/TAO/USDC/BTC), cherche la
transaction source correspondante côté exchange (TRANSFER_OUT / STAKING /
retraits Kraken & Binance) autour de la même date et quantité, avec ses notes
et external_id — pour décider si le mirror décrit un événement réel (retrait
effectif vers Tangem) ou un fantôme (reward de staking mal interprété, etc.).
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> None:
    engine = create_async_engine(_url(), echo=False)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
            SELECT a.symbol, t.transaction_type, t.quantity, t.executed_at,
                   t.exchange, COALESCE(t.external_id,'') AS ext,
                   COALESCE(t.notes,'') AS notes
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE a.symbol = ANY(:syms)
              AND t.executed_at BETWEEN '2026-06-04' AND '2026-06-09'
            ORDER BY a.symbol, t.executed_at
            """
                ),
                {"syms": ["ETH", "SOL", "USDC", "BTC", "TAO"]},
            )
        ).all()
        print("=== TOUTES transactions 4-9 juin (tous exchanges) ===")
        for sym, ttype, qty, dt, exch, ext, notes in rows:
            print(f"  {dt}  {sym:<5} {ttype:<14} {qty}  @{exch or '?'}  ext={ext[:40]}  {notes[:70]}")

        rows2 = (
            await conn.execute(
                text(
                    """
            SELECT a.symbol, t.transaction_type, t.quantity, t.executed_at,
                   t.exchange, COALESCE(t.external_id,'') AS ext,
                   COALESCE(t.notes,'') AS notes, t.fee
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE a.symbol = ANY(:syms)
              AND t.executed_at BETWEEN '2026-06-27' AND '2026-06-30'
            ORDER BY a.symbol, t.executed_at
            """
                ),
                {"syms": ["ETH", "SOL", "USDC", "TAO"]},
            )
        ).all()
        print("\n=== TOUTES transactions 27-30 juin (retrait Binance -> Tangem) ===")
        for sym, ttype, qty, dt, exch, ext, notes, fee in rows2:
            print(f"  {dt}  {sym:<5} {ttype:<14} {qty} fee={fee}  @{exch or '?'}  ext={ext[:40]}  {notes[:60]}")

        rows3 = (
            await conn.execute(
                text(
                    """
            SELECT a.symbol, t.transaction_type, t.quantity, t.executed_at::date,
                   COALESCE(t.notes,'') AS notes
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE a.symbol = 'USDC' AND t.exchange ILIKE '%kraken%'
              AND t.executed_at BETWEEN '2026-06-01' AND '2026-06-08'
            ORDER BY t.executed_at
            """
                )
            )
        ).all()
        print("\n=== USDC côté Kraken 1-8 juin (source du mirror 34.80) ===")
        for sym, ttype, qty, dt, notes in rows3:
            print(f"  {dt}  {ttype:<14} {qty}  {notes[:70]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
