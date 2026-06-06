"""Dry-run / apply insertion des 2 AIRDROP PEPE vouchers Binance."""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PEPE_BINANCE_ASSET_ID = "a13869c6-f3df-41db-b1a2-92d96356c37b"
EXECUTED_AT = datetime(2026, 3, 25, 0, 7, 0, tzinfo=timezone.utc)
PEPE_PRICE_EUR = Decimal("0.00000344")  # PEPE/USD 4e-6 ÷ EUR/USD 1.1615
QTY_PER_VOUCHER = Decimal("20000")

INSERT = """
    INSERT INTO transactions (
        id, asset_id, transaction_type, quantity, price, fee, fee_currency,
        currency, conversion_rate, executed_at, exchange, external_id,
        notes, created_at
    )
    VALUES (
        gen_random_uuid(),
        :asset_id,
        'AIRDROP',
        :qty,
        :price,
        0,
        'EUR',
        'EUR',
        1,
        :executed_at,
        'Binance',
        :ext_id,
        :notes,
        NOW()
    )
    RETURNING id::text, transaction_type::text, quantity, external_id
"""


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    return url


VOUCHERS = [
    {
        "asset_id": PEPE_BINANCE_ASSET_ID,
        "qty": QTY_PER_VOUCHER,
        "price": PEPE_PRICE_EUR,
        "executed_at": EXECUTED_AT,
        "ext_id": "voucher_binance_PEPE_20k_1_20260325",
        "notes": "Binance reward voucher token: 20000 PEPE (utilisé le 2026-03-25 00:07)",
    },
    {
        "asset_id": PEPE_BINANCE_ASSET_ID,
        "qty": QTY_PER_VOUCHER,
        "price": PEPE_PRICE_EUR,
        "executed_at": EXECUTED_AT,
        "ext_id": "voucher_binance_PEPE_20k_2_20260325",
        "notes": "Binance reward voucher token: 20000 PEPE (utilisé le 2026-03-25 00:07)",
    },
]


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="actually insert (default: dry-run)")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    async with eng.connect() as conn:
        # 1. Sanity: asset exists & symbol matches
        a = (
            (
                await conn.execute(
                    text("SELECT symbol, exchange, quantity FROM assets WHERE id = :aid"),
                    {"aid": PEPE_BINANCE_ASSET_ID},
                )
            )
            .mappings()
            .first()
        )
        if not a:
            print(f"FATAL: asset {PEPE_BINANCE_ASSET_ID} not found.")
            return 2
        if a["symbol"] != "PEPE" or a["exchange"] != "Binance":
            print(f"FATAL: asset is not PEPE/Binance ({a['symbol']}/{a['exchange']}).")
            return 2
        print(f"Target asset OK: {a['symbol']} on {a['exchange']}, current stored qty={a['quantity']}")

        # 2. Sanity: external_ids not already present
        for v in VOUCHERS:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM transactions WHERE external_id = :eid"),
                    {"eid": v["ext_id"]},
                )
            ).first()
            if exists:
                print(f"FATAL: external_id '{v['ext_id']}' already exists — refusing to insert duplicates.")
                return 2
        print("External_ids free of conflict.")

        print()
        print("Planned INSERTs:")
        for v in VOUCHERS:
            print(f"  AIRDROP qty={v['qty']} price={v['price']} EUR executed_at={v['executed_at']} ext={v['ext_id']}")

        if not args.apply:
            print("\nDry-run: nothing written. Re-run with --apply.")
            return 0

    # Apply with a single transaction
    async with eng.begin() as tx_conn:
        inserted = []
        for v in VOUCHERS:
            row = (await tx_conn.execute(text(INSERT), v)).mappings().first()
            inserted.append(row)
        print("\nInserted rows:")
        for r in inserted:
            print(f"  id={r['id']} type={r['transaction_type']} qty={r['quantity']} ext={r['external_id']}")
    await eng.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
