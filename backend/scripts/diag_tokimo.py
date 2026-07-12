"""Read-only : détail des versements Tokimo pour expliquer l'écart
« gains réalisés Tokimo (8,72) vs intérêts encaissés InvestAI (7,68) ».
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
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> None:
    engine = create_async_engine(_url(), echo=False)
    async with engine.connect() as conn:
        projects = (
            await conn.execute(
                text(
                    """
            SELECT p.id::text, p.project_name, p.platform, p.status, p.invested_amount,
                   p.annual_rate, p.total_received, p.tax_rate
            FROM crowdfunding_projects p
            WHERE p.platform ILIKE '%tokimo%'
            ORDER BY p.created_at
            """
                )
            )
        ).all()
        for pid, name, platform, status, invested, rate, received, tax in projects:
            print(
                f"\n=== {name} @ {platform}  status={status} investi={invested} taux={rate}% tax_rate={tax} total_received={received} ==="
            )
            reps = (
                await conn.execute(
                    text(
                        """
                SELECT payment_date, amount, payment_type, interest_amount,
                       capital_amount, tax_amount, COALESCE(notes,'')
                FROM crowdfunding_repayments WHERE project_id = CAST(:pid AS uuid)
                ORDER BY payment_date
                """
                    ),
                    {"pid": pid},
                )
            ).all()
            tot_i = tot_c = tot_t = tot_a = 0.0
            for dt, amount, ptype, i, c, t, notes in reps:
                print(f"  {dt}  amount={amount}  type={ptype}  interest={i}  capital={c}  tax={t}  {notes[:50]}")
                tot_a += float(amount or 0)
                tot_i += float(i or 0)
                tot_c += float(c or 0)
                tot_t += float(t or 0)
            print(f"  → Σ amount={tot_a:.2f}  Σ interest={tot_i:.2f}  Σ capital={tot_c:.2f}  Σ tax={tot_t:.2f}")
            print(f"  → interest+tax (brut avant retenue) = {tot_i + tot_t:.2f}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
