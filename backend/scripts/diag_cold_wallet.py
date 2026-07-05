"""Read-only diagnostic: cold-wallet quantities vs their transaction history.

Usage: DATABASE_URL=postgresql://... python -m scripts.diag_cold_wallet
Prints, for each cold-wallet asset, the stored quantity, the signed sum of its
transactions, and the full transaction list — to localise reconciliation gaps
against the real on-chain balance (e.g. Tangem).
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

SYMBOLS = ("ETH", "SOL", "TAO", "USDC", "BTC", "PAXG")

IN_TYPES = {"BUY", "TRANSFER_IN", "CONVERSION_IN", "AIRDROP", "STAKING_REWARD"}
OUT_TYPES = {"SELL", "TRANSFER_OUT", "CONVERSION_OUT"}


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
        assets = (
            await conn.execute(
                text(
                    """
            SELECT a.id::text, a.symbol, a.exchange, a.quantity, a.avg_buy_price
            FROM assets a
            WHERE a.symbol = ANY(:syms)
              AND (a.exchange ILIKE '%cold%' OR a.exchange ILIKE '%tangem%' OR a.exchange ILIKE '%wallet%')
            ORDER BY a.symbol
            """
                ),
                {"syms": list(SYMBOLS)},
            )
        ).all()

        for aid, sym, exch, qty, avg in assets:
            print(f"\n=== {sym} @ {exch}  stored_qty={qty}  avg_buy={avg} ===")
            txs = (
                await conn.execute(
                    text(
                        """
                SELECT transaction_type, quantity, price, fee, executed_at::date,
                       exchange, COALESCE(notes,'')
                FROM transactions WHERE asset_id = :aid
                ORDER BY executed_at NULLS FIRST
                """
                    ),
                    {"aid": aid},
                )
            ).all()
            total = Decimal("0")
            for ttype, tqty, price, fee, dt, texch, notes in txs:
                q = Decimal(str(tqty))
                sign = "+" if ttype in IN_TYPES else "-" if ttype in OUT_TYPES else " "
                if ttype in IN_TYPES:
                    total += q
                elif ttype in OUT_TYPES:
                    total -= q
                print(f"  {dt}  {ttype:<14} {sign}{q}  px={price} fee={fee}  {texch or ''} {notes[:60]}")
            print(f"  → somme des transactions = {total}   (stored = {qty})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
