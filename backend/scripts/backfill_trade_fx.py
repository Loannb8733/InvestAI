"""Deterministic FX backfill for legacy transactions (FIN-01).

Context
-------
Before FIN-01, the exchange sync hard-coded ``currency="EUR"`` and left
``conversion_rate=NULL`` on every synced trade. For non-EUR trades this understates
or overstates the EUR cost basis by the FX delta (~8-9% for USD-quoted history). The
sync is now fixed going forward; this script repairs the rows already in the database.

Scope (conservative, but wider than fiat-only)
---------------------------------------------
We touch a row only when its original quote currency is *recoverable with certainty*
from what the database still holds. The pair symbol is gone (``transactions`` keeps the
base asset only), so ``fee_currency`` is the sole clue, and its worth is exchange-
dependent: Kraken stores the quote there by construction, Binance stores the received
asset, BNB, or the quote depending on the side and fee settings.

:func:`fee_currency_quote_anchor` encodes the one discriminant valid for both — a fee
charged in the row's own asset proves nothing, a fee charged in another fiat/USD-stable
can only be the quote — so order-book trades are now covered wherever that holds, and
skipped (never guessed) everywhere else. Rows whose fee was paid in BNB remain
unrecoverable by design; they are reported, not silently dropped.

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

from sqlalchemy import or_, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.transaction import Transaction, TransactionType  # noqa: E402
from app.services.exchanges.pair_utils import fee_currency_quote_anchor  # noqa: E402
from app.services.fx_history_service import FxHistoryService  # noqa: E402

# Synced row kinds whose fee_currency is the fiat the user actually paid in.
# "Instant Buy" was missing here even though the live sync already resolves its FX.
_RECOVERABLE_NOTES = ("Fiat Order", "Auto-Invest DCA", "Instant Buy")
# Order-book trades carry no notes; they are reached by type instead.
_ORDER_BOOK_TYPES = (TransactionType.BUY, TransactionType.SELL)
# Frankfurter (ECB) history is plentiful from 1999; 2017 covers all real crypto history.
_EARLIEST = date(2017, 1, 1)


async def backfill(commit: bool) -> None:
    async with AsyncSessionLocal() as db:
        fx = FxHistoryService(db)

        # Candidate rows: any synced, not-yet-FX-resolved row whose kind can carry a
        # recoverable quote — fiat/instant/DCA purchases, plus order-book trades.
        # Joined to Asset because the discriminant compares fee_currency to the row's
        # own asset symbol. `exchange != ""` keeps manual/CSV rows out: those never went
        # through the sync, so their fee_currency follows no known convention.
        result = await db.execute(
            select(Transaction, Asset.symbol)
            .join(Asset, Asset.id == Transaction.asset_id)
            .where(
                Transaction.conversion_rate.is_(None),
                Transaction.currency == "EUR",
                Transaction.fee_currency.isnot(None),
                Transaction.executed_at.isnot(None),
                Transaction.exchange.isnot(None),
                Transaction.exchange != "",
                or_(
                    Transaction.notes.in_(_RECOVERABLE_NOTES),
                    Transaction.transaction_type.in_(_ORDER_BOOK_TYPES),
                ),
            )
        )
        rows = list(result.all())
        print(f"Found {len(rows)} synced candidate rows with NULL conversion_rate.")

        # Determine which non-EUR anchors we actually need, then seed each once.
        anchors_needed: set[str] = set()
        for tx, asset_symbol in rows:
            anchor = fee_currency_quote_anchor(tx.fee_currency, asset_symbol)
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
        skipped_unprovable = Counter()
        skipped_no_rate = Counter()
        for tx, asset_symbol in rows:
            anchor = fee_currency_quote_anchor(tx.fee_currency, asset_symbol)
            if anchor is None:
                # Fee paid in the asset itself, in BNB, or in an unknown symbol: the
                # quote cannot be proven, so the row is left exactly as it is.
                skipped_unprovable[(tx.fee_currency or "?").upper()] += 1
                continue
            if anchor == "EUR":
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
        print(f"Left as EUR (quote already EUR): {skipped_eur}")
        if skipped_unprovable:
            # Reported, never silently dropped: this is the residual FIN-01 exposure.
            total = sum(skipped_unprovable.values())
            print(f"Left as EUR (quote not provable from fee currency): {total}")
            for fc, n in sorted(skipped_unprovable.items(), key=lambda kv: -kv[1]):
                print(f"    fee in {fc} : {n}")
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
