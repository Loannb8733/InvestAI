"""Fix 9 Convert OUT transactions whose stored price is < 0.1x market.

Same bug family as USDT convert_sell_00bc9edbd... (fixed in PR #214) but
mirrored: ratio inverted produces a TOO-LOW EUR price instead of the
240k EUR/USDT outlier. Each of these underprices the EUR cost basis of
a Convert OUT, hiding ~550 EUR of legitimate realized P&L.

Strategy: pick the price from asset_price_history within +/- 3 days of
executed_at. If unavailable, skip.

Idempotent: skip if current ratio already > 0.1 (already fixed).

Dry-run by default. --apply to write.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

RATIO_THRESHOLD = Decimal("0.1")


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
        rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT t.id::text AS tid, t.quantity AS qty, t.price AS px,
                       t.executed_at::date AS d, a.symbol, a.exchange,
                       t.external_id
                FROM transactions t
                JOIN assets a ON a.id = t.asset_id
                WHERE a.asset_type != 'CROWDFUNDING'
                  AND t.transaction_type = 'CONVERSION_OUT'
                  AND t.price > 0
                  AND t.quantity > 0
                ORDER BY t.executed_at
                """
                    )
                )
            )
            .mappings()
            .all()
        )

        # Get market price within +/- 3 days
        async def market(sym: str, date) -> Decimal | None:
            for offset in (0, -1, 1, -2, 2, -3, 3):
                cand = date + timedelta(days=offset)
                r = (
                    await conn.execute(
                        text(
                            "SELECT price_eur FROM asset_price_history" " WHERE symbol = :s AND price_date = :d LIMIT 1"
                        ),
                        {"s": sym, "d": cand},
                    )
                ).first()
                if r and r[0] and D(r[0]) > 0:
                    return D(r[0])
            return None

        fixed = 0
        skipped = 0
        for r in rows:
            px = D(r["px"])
            mkt = await market(r["symbol"], r["d"])
            if mkt is None:
                continue
            ratio = px / mkt
            if ratio >= RATIO_THRESHOLD:
                continue  # not aberrant or already fixed
            # Print before/after
            print(
                f"  {r['d']} {r['symbol']:<6} qty={float(r['qty']):>14.6f}"
                f"  old_px={float(px):>14.8f}  new_px={float(mkt):>14.6f}"
                f"  ratio={float(ratio):.4f}  ext={(r['external_id'] or '')[:30]}"
            )
            if args.apply:
                await conn.execute(
                    text("UPDATE transactions SET price = :p WHERE id = :tid"),
                    {"p": mkt, "tid": r["tid"]},
                )
            fixed += 1

        print(f"\n{fixed} transaction(s) " + ("corrigees." if args.apply else "a corriger (dry-run)."))
        if not args.apply:
            print("Re-run avec --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
