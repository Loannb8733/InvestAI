"""Repair Transfer chaining + cost basis from P2.8 audit.

Fixes identified by _audit_transfers.py (read-only):

1. PAXG Kraken -> Tangem 2026-02-24: TRANSFER_IN price = 0
   -> set price = market(PAXG, 2026-02-24) from asset_price_history
   -> recovers ~88 EUR of cost basis carried into Tangem

2. USDT Bybit -> Binance 2026-05-05: matched pair without
   related_transaction_id on either leg (residual after PR #215
   duplicate cleanup that nulled the FK)
   -> SET related_transaction_id mutually on both legs

3. BTC + ETH Crypto.com -> Tangem 2026-02-24: matched-by-context
   (same date, same direction, similar order of magnitude) but
   missed by the 5% quantity tolerance in the audit because of
   network fees (BTC fee ~17%, ETH fee ~36%).
   -> SET related_transaction_id mutually on both legs
   -> Preserve the IN cost basis as-is (Tangem cold wallet, value
     carries from the OUT leg's avg cost).

Dry-run by default. --apply to write.
Idempotent (skip if already chained / priced).
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


def D(v):
    return Decimal(str(v or 0))


def _database_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def find_one(conn, *, symbol, exchange, tt, executed_date, qty_min=None, qty_max=None):
    """Find a unique transaction matching the predicates."""
    sql = (
        "SELECT t.id::text AS tid, t.quantity AS qty, t.price AS px,"
        " t.related_transaction_id::text AS rel"
        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
        " WHERE a.symbol = :s AND a.exchange = :e"
        "   AND t.transaction_type = :tt"
        "   AND t.executed_at::date = :d"
    )
    params = {"s": symbol, "e": exchange, "tt": tt, "d": executed_date}
    if qty_min is not None:
        sql += " AND t.quantity >= :qmin"
        params["qmin"] = qty_min
    if qty_max is not None:
        sql += " AND t.quantity <= :qmax"
        params["qmax"] = qty_max
    rows = (await conn.execute(text(sql), params)).mappings().all()
    if not rows:
        return None
    if len(rows) > 1:
        # Prefer the one with largest qty (fee-adjusted match for the IN leg)
        rows = sorted(rows, key=lambda r: float(r["qty"]), reverse=True)
    return rows[0]


async def chain_pair(conn, out_row, in_row, *, label: str, apply: bool):
    if not out_row or not in_row:
        print(f"  [{label}] missing leg(s), skip")
        return False
    if (out_row["rel"] == in_row["tid"]) and (in_row["rel"] == out_row["tid"]):
        print(f"  [{label}] already chained, skip")
        return False
    print(
        f"  [{label}] chain  OUT={out_row['tid'][:8]} <-> IN={in_row['tid'][:8]}  "
        f"qty OUT={float(out_row['qty']):.6f} IN={float(in_row['qty']):.6f}"
    )
    if apply:
        # Set both directions
        await conn.execute(
            text("UPDATE transactions SET related_transaction_id = :rel WHERE id = :tid"),
            {"rel": in_row["tid"], "tid": out_row["tid"]},
        )
        await conn.execute(
            text("UPDATE transactions SET related_transaction_id = :rel WHERE id = :tid"),
            {"rel": out_row["tid"], "tid": in_row["tid"]},
        )
    return True


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    eng = create_async_engine(_database_url(), echo=False)

    async with eng.begin() as conn:
        from datetime import date as _date

        # ── 1. PAXG zero-basis fix ──────────────────────────────
        print("=== 1. PAXG IN price = 0 (Kraken -> Tangem) ===")
        paxg_in = await find_one(
            conn,
            symbol="PAXG",
            exchange="Tangem",
            tt="TRANSFER_IN",
            executed_date=_date(2026, 2, 24),
        )
        if not paxg_in:
            print("  PAXG IN not found, skip")
        elif D(paxg_in["px"]) > 0:
            print(f"  PAXG IN already priced ({paxg_in['px']}), skip")
        else:
            mkt = None
            for offset in (0, -1, 1, -2, 2, -3, 3):
                cand = _date(2026, 2, 24) + timedelta(days=offset)
                r = (
                    await conn.execute(
                        text(
                            "SELECT price_eur FROM asset_price_history"
                            " WHERE symbol='PAXG' AND price_date = :d LIMIT 1"
                        ),
                        {"d": cand},
                    )
                ).first()
                if r and r[0] and D(r[0]) > 0:
                    mkt = D(r[0])
                    break
            if mkt is None:
                print("  PAXG market price unavailable, skip")
            else:
                print(
                    f"  PAXG IN price 0 -> {float(mkt):.4f}  "
                    f"(qty={float(paxg_in['qty']):.6f}, value recovered {float(mkt * D(paxg_in['qty'])):.2f} EUR)"
                )
                if args.apply:
                    await conn.execute(
                        text("UPDATE transactions SET price = :p WHERE id = :tid"),
                        {"p": mkt, "tid": paxg_in["tid"]},
                    )

        # ── 2. USDT Bybit -> Binance chaining ───────────────────
        print("\n=== 2. USDT Bybit -> Binance chain ===")
        usdt_out = await find_one(
            conn,
            symbol="USDT",
            exchange="Bybit",
            tt="TRANSFER_OUT",
            executed_date=_date(2026, 5, 5),
            qty_min=Decimal("148"),
            qty_max=Decimal("149"),
        )
        usdt_in = await find_one(
            conn,
            symbol="USDT",
            exchange="Binance",
            tt="TRANSFER_IN",
            executed_date=_date(2026, 5, 4),
            qty_min=Decimal("148"),
            qty_max=Decimal("149"),
        )
        await chain_pair(conn, usdt_out, usdt_in, label="USDT Bybit->Binance", apply=args.apply)

        # ── 3. BTC Crypto.com -> Tangem chaining ────────────────
        print("\n=== 3. BTC Crypto.com -> Tangem chain (fee tolerance) ===")
        btc_out = await find_one(
            conn,
            symbol="BTC",
            exchange="Crypto.com",
            tt="TRANSFER_OUT",
            executed_date=_date(2026, 2, 24),
        )
        btc_in = await find_one(
            conn,
            symbol="BTC",
            exchange="Tangem",
            tt="TRANSFER_IN",
            executed_date=_date(2026, 2, 24),
            qty_min=Decimal("0.0005"),
            qty_max=Decimal("0.002"),
        )
        await chain_pair(conn, btc_out, btc_in, label="BTC Crypto.com->Tangem", apply=args.apply)

        # ── 4. ETH Crypto.com -> Tangem chaining ────────────────
        print("\n=== 4. ETH Crypto.com -> Tangem chain (fee tolerance) ===")
        eth_out = await find_one(
            conn,
            symbol="ETH",
            exchange="Crypto.com",
            tt="TRANSFER_OUT",
            executed_date=_date(2026, 2, 24),
        )
        eth_in = await find_one(
            conn,
            symbol="ETH",
            exchange="Tangem",
            tt="TRANSFER_IN",
            executed_date=_date(2026, 2, 24),
            qty_min=Decimal("0.005"),
            qty_max=Decimal("0.02"),
        )
        await chain_pair(conn, eth_out, eth_in, label="ETH Crypto.com->Tangem", apply=args.apply)

    if not args.apply:
        print("\nDry-run. Re-run avec --apply.")
    else:
        print("\nApplique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
