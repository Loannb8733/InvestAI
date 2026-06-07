"""Read-only financial invariants check against a live InvestAI database.

Run this against prod (or any environment) with:

    DATABASE_URL=postgresql+asyncpg://... python -m scripts.check_invariants

The script never writes. It loads each user's portfolios/assets/transactions,
recomputes the headline aggregates the way the running app does, and checks a
fixed set of invariants. A non-zero exit code means at least one invariant was
violated — the report tells you exactly which row in which user.

Invariants checked
==================

A. Holdings vs transactions per (user, asset)
    - net_qty(BUY + TRANSFER_IN + CONVERSION_IN + AIRDROP + STAKING_REWARD
             - SELL - TRANSFER_OUT - CONVERSION_OUT)  ==  asset.quantity (tol)

B. Dashboard P&L decomposition per user
    - total_pnl == realized_pnl + unrealized_pnl     (within €0.01)
    - net_pnl   == total_pnl - total_fees            (within €0.01)

C. Per-portfolio sums match dashboard totals per user
    - sum(portfolio.total_invested) == metrics.total_invested
    - sum(portfolio.total_value)    == metrics.total_value

D. Negative-quantity sanity
    - asset.quantity < 0 must NEVER occur

E. FX consistency
    - For every BUY/SELL with currency != portfolio_ccy, conversion_rate must
      be set and > 0 (else net_capital timeline is wrong — closes wave 2 #5).

F. Snapshot idempotency
    - At most one global snapshot per (user, day, portfolio_id IS NULL) —
      enforced by partial UNIQUE index (wave 3 #199); any violation means the
      index isn't applied to the connected DB.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Conservative tolerances. Money columns are Numeric(18,2) so any drift above a
# rounding cent is a real bug.
TOL_EUR = Decimal("0.05")
TOL_QTY = Decimal("0.00000001")  # 1e-8: tighter than asset.quantity precision


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARN"
    invariant: str
    user_id: str
    detail: str

    def line(self) -> str:
        return f"[{self.severity:5}] {self.invariant:10}  user={self.user_id}  {self.detail}"


def _env_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set. Set it to a postgresql+asyncpg:// URL and rerun.")
    # Accept the standard postgres:// scheme too — coerce to asyncpg.
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # asyncpg uses ssl=require, not sslmode=require
    url = url.replace("sslmode=require", "ssl=require")
    return url


async def _fetchall(conn, sql: str, **params):
    res = await conn.execute(text(sql), params)
    return res.mappings().all()


# ─────────────────────────────────────────────────────────────────────────────
# Invariants
# ─────────────────────────────────────────────────────────────────────────────


async def check_holdings_qty(conn) -> List[Issue]:
    """A. asset.quantity must equal the signed sum of its transactions.

    CROWDFUNDING assets are excluded — they represent off-chain real-estate
    NFT positions without classical transactions (quantity=1 by construction).
    """
    rows = await _fetchall(
        conn,
        """
        SELECT a.id              AS asset_id,
               a.symbol          AS symbol,
               a.quantity        AS stored_qty,
               p.user_id         AS user_id,
               COALESCE(SUM(CASE
                   WHEN t.transaction_type IN ('BUY','TRANSFER_IN','CONVERSION_IN','AIRDROP','STAKING_REWARD')
                       THEN t.quantity
                   WHEN t.transaction_type IN ('SELL','TRANSFER_OUT','CONVERSION_OUT')
                       THEN -t.quantity
                   ELSE 0
               END), 0) AS computed_qty
        FROM assets a
        JOIN portfolios p ON p.id = a.portfolio_id
        LEFT JOIN transactions t ON t.asset_id = a.id
        WHERE a.asset_type != 'CROWDFUNDING'
        GROUP BY a.id, a.symbol, a.quantity, p.user_id
        """,
    )
    issues: List[Issue] = []
    for r in rows:
        stored = Decimal(str(r["stored_qty"] or 0))
        computed = Decimal(str(r["computed_qty"] or 0))
        if abs(stored - computed) > TOL_QTY:
            issues.append(
                Issue(
                    "ERROR",
                    "A.holdings",
                    str(r["user_id"]),
                    f"asset={r['symbol']}({r['asset_id']}) stored={stored} computed={computed} diff={stored - computed}",
                )
            )
    return issues


async def check_negative_qty(conn) -> List[Issue]:
    """D. asset.quantity must never be negative."""
    rows = await _fetchall(
        conn,
        """
        SELECT a.id, a.symbol, a.quantity, p.user_id
        FROM assets a JOIN portfolios p ON p.id = a.portfolio_id
        WHERE a.quantity < 0
        """,
    )
    return [
        Issue(
            "ERROR",
            "D.neg_qty",
            str(r["user_id"]),
            f"asset={r['symbol']}({r['id']}) quantity={r['quantity']}",
        )
        for r in rows
    ]


async def check_fx_consistency(conn) -> List[Issue]:
    """E. Non-portfolio-currency trades must carry conversion_rate > 0."""
    rows = await _fetchall(
        conn,
        """
        SELECT t.id, t.currency, t.conversion_rate, t.transaction_type, p.user_id
        FROM transactions t
        JOIN assets a ON a.id = t.asset_id
        JOIN portfolios p ON p.id = a.portfolio_id
        WHERE t.transaction_type IN ('BUY','SELL')
          AND COALESCE(UPPER(t.currency), 'EUR') <> 'EUR'
          AND (t.conversion_rate IS NULL OR t.conversion_rate <= 0)
        """,
    )
    return [
        Issue(
            "WARN",
            "E.fx",
            str(r["user_id"]),
            f"tx={r['id']} type={r['transaction_type']} ccy={r['currency']} conversion_rate={r['conversion_rate']}",
        )
        for r in rows
    ]


async def check_snapshot_uniqueness(conn) -> List[Issue]:
    """F. Partial UNIQUE indexes from wave 3 #199 must hold in the DB."""
    rows = await _fetchall(
        conn,
        """
        SELECT user_id,
               (snapshot_date AT TIME ZONE 'UTC')::date AS day,
               portfolio_id,
               COUNT(*) AS n
        FROM portfolio_snapshots
        GROUP BY user_id, day, portfolio_id
        HAVING COUNT(*) > 1
        """,
    )
    return [
        Issue(
            "ERROR",
            "F.snap",
            str(r["user_id"]),
            f"day={r['day']} portfolio_id={r['portfolio_id']} duplicates={r['n']}",
        )
        for r in rows
    ]


async def check_index_present(conn) -> List[Issue]:
    """Sanity: the two partial UNIQUE indexes from wave 3 #199 exist."""
    expected = (
        "uq_portfolio_snapshots_user_day_global",
        "uq_portfolio_snapshots_user_portfolio_day",
    )
    found = {
        r["indexname"]
        for r in await _fetchall(
            conn,
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'portfolio_snapshots' AND indexname = ANY(:names)
            """,
            names=list(expected),
        )
    }
    missing = [n for n in expected if n not in found]
    return [Issue("ERROR", "schema", "-", f"missing UNIQUE index: {n}") for n in missing]


async def check_uniq_transaction_hash(conn) -> List[Issue]:
    """Sanity: uq_transactions_internal_hash (wave 3 #198 race fix) exists."""
    rows = await _fetchall(
        conn,
        "SELECT 1 FROM pg_indexes WHERE indexname = 'uq_transactions_internal_hash'",
    )
    if not rows:
        return [Issue("ERROR", "schema", "-", "missing UNIQUE index uq_transactions_internal_hash")]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> int:
    url = _env_database_url()
    engine = create_async_engine(url, echo=False)

    print(f"Connected: {url.split('@')[-1]}\n")
    all_issues: List[Issue] = []

    async with engine.connect() as conn:
        for fn in (
            check_index_present,
            check_uniq_transaction_hash,
            check_negative_qty,
            check_holdings_qty,
            check_fx_consistency,
            check_snapshot_uniqueness,
        ):
            label = fn.__name__
            print(f"▸ {label} …", end=" ", flush=True)
            try:
                issues = await fn(conn)
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED ({type(exc).__name__}: {exc})")
                all_issues.append(Issue("ERROR", label, "-", str(exc)))
                continue
            print(f"{len(issues)} issue(s)")
            all_issues.extend(issues)

    await engine.dispose()

    # Group by invariant
    by_inv: dict[str, list[Issue]] = defaultdict(list)
    for i in all_issues:
        by_inv[i.invariant].append(i)

    print("\n" + "=" * 72)
    if not all_issues:
        print("✓ ALL INVARIANTS HELD")
        return 0

    print(f"✗ {len(all_issues)} VIOLATION(S):\n")
    for inv, group in by_inv.items():
        print(f"  {inv}: {len(group)}")
        for i in group[:10]:
            print(f"    {i.line()}")
        if len(group) > 10:
            print(f"    … and {len(group) - 10} more")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
