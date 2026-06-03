"""Deterministic FX backfill for legacy transactions (FIN-01).

Context
-------
Before FIN-01, the exchange sync hard-coded ``currency="EUR"`` and left
``conversion_rate=NULL`` on every synced trade. For non-EUR trades this understates
or overstates the EUR cost basis by the FX delta (~8-9% for USD-quoted history). The
sync is now fixed going forward; this script repairs the rows already in the database.

Scope (deliberately conservative)
---------------------------------
We only touch rows where the original quote currency is *recoverable with certainty*:
fiat orders and auto-invest (DCA) rows, whose ``fee_currency`` holds the real fiat
currency the user paid in. Normal order-book trades are NOT touched here — their
``fee_currency`` is typically the received asset or BNB, not the quote, so inferring
their currency would be a guess. They keep ``currency='EUR'`` until a separate,
explicitly-chosen strategy handles them.

Safety
------
- **Dry-run by default.** Pass ``--commit`` to actually write.
- **Idempotent.** Only rows with ``conversion_rate IS NULL`` are considered, so
  re-running never double-applies.
- A row is updated only when a *valid* historical rate exists; otherwise it is left
  untouched and counted as skipped (never silently set to rate=1).

Usage
-----
    # inside the backend container
    python scripts/backfill_trade_fx.py            # dry-run, prints what would change
    python scripts/backfill_trade_fx.py --commit   # apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.services.exchanges.pair_utils import quote_fx_currency  # noqa: E402
from app.services.fx_history_service import FxHistoryService  # noqa: E402

# Only these synced row kinds retain the real fiat currency in fee_currency.
_RECOVERABLE_NOTES = ("Fiat Order", "Auto-Invest DCA")
# Frankfurter (ECB) history is plentiful from 1999; 2017 covers all real crypto history.
_EARLIEST = date(2017, 1, 1)


async def backfill(commit: bool) -> None:
    async with AsyncSessionLocal() as db:
        fx = FxHistoryService(db)

        # Candidate rows: synced fiat/auto-invest, not yet FX-resolved.
        result = await db.execute(
            select(Transaction).where(
                Transaction.conversion_rate.is_(None),
                Transaction.currency == "EUR",
                Transaction.notes.in_(_RECOVERABLE_NOTES),
                Transaction.fee_currency.isnot(None),
                Transaction.executed_at.isnot(None),
            )
        )
        rows = list(result.scalars().all())
        print(f"Found {len(rows)} candidate fiat/auto-invest rows with NULL conversion_rate.")

        # Determine which non-EUR anchors we actually need, then seed each once.
        anchors_needed: set[str] = set()
        for tx in rows:
            anchor = quote_fx_currency(tx.fee_currency)
            if anchor and anchor != "EUR":
                anchors_needed.add(anchor)
        for anchor in sorted(anchors_needed):
            try:
                inserted = await fx.ensure_seeded(anchor, "EUR", _EARLIEST)
                print(f"  seeded {anchor}->EUR (+{inserted} daily rows)")
            except Exception as e:  # noqa: BLE001
                print(f"  WARNING: could not seed {anchor}->EUR ({e}); those rows will be skipped")

        updated = Counter()
        skipped_eur = 0
        skipped_no_rate = Counter()
        for tx in rows:
            anchor = quote_fx_currency(tx.fee_currency)
            if anchor is None or anchor == "EUR":
                skipped_eur += 1
                continue
            rate = await fx.get_rate(tx.executed_at.date(), anchor, "EUR")
            if rate is None:
                skipped_no_rate[anchor] += 1
                continue
            tx.currency = anchor
            tx.conversion_rate = Decimal(str(rate))
            updated[anchor] += 1

        print("\n--- Summary ---")
        print(f"Would update: {sum(updated.values())} rows")
        for anchor, n in sorted(updated.items()):
            print(f"    {anchor}->EUR : {n}")
        print(f"Left as EUR (quote already EUR/unknown): {skipped_eur}")
        if skipped_no_rate:
            print("Skipped (no historical rate found):")
            for anchor, n in sorted(skipped_no_rate.items()):
                print(f"    {anchor} : {n}")

        if commit:
            await db.commit()
            print("\nCOMMITTED.")
        else:
            await db.rollback()
            print("\nDRY-RUN: no changes written. Re-run with --commit to apply.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic FX backfill (FIN-01).")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default: dry-run).")
    args = parser.parse_args()
    asyncio.run(backfill(args.commit))


if __name__ == "__main__":
    main()
