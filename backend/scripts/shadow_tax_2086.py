"""Shadow-compare the 2086 tax computation: legacy vs converged, on real data.

Run against prod (or any environment) WITHOUT writing anything:

    DATABASE_URL=postgresql://...  python -m scripts.shadow_tax_2086
    DATABASE_URL=postgresql://...  python -m scripts.shadow_tax_2086 --years 2024 2025 2026

For every (user, year) it runs ``ReportService.compute_tax_2086`` twice — once
with ``report_service.TAX_MODE_LEGACY`` (the exact behaviour before the four
accidental 2086 bugs were fixed) and once with the default converged mode — and
prints every difference in the headline numbers and per-event fields.

Purpose: quantify the real-world impact of the convergence on YOUR data before
trusting it. A clean run (no differences) means the fixes touch nothing in this
dataset; any line printed is a cession whose taxable figure changed.

The four converged fixes (see report_service.TAX_MODE docstrings):
  1. deterministic ordering (TRANSFER_OUT before same-timestamp TRANSFER_IN),
  2. external_id conversion-match fallback,
  3. transfer network-fee trim,
  4. unmatched CONVERSION_OUT preserved (not consumed + taxed).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.user import User
from app.services import report_service
from app.services.report_service import ReportService

# A field difference below this (in EUR) is treated as float noise, not a change.
EPS = 0.005


def _env_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set. Set it to a postgresql:// URL and rerun.")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    return url


def _summary_fields(s) -> dict:
    return {
        "nb_cessions": s.nb_cessions,
        "nb_court_terme": s.nb_court_terme,
        "nb_long_terme": s.nb_long_terme,
        "total_cessions": round(float(s.total_cessions), 2),
        "net_plus_value": round(float(s.net_plus_value), 2),
        "flat_tax_30": round(float(s.flat_tax_30), 2),
    }


def _event_key(ev) -> tuple:
    return (str(ev.date), ev.symbol, ev.event_type, round(float(ev.quantity), 8))


def _diff_summary(legacy, converged) -> list:
    out = []
    a, b = _summary_fields(legacy), _summary_fields(converged)
    for k in a:
        if isinstance(a[k], int):
            if a[k] != b[k]:
                out.append(f"    summary.{k}: {a[k]} -> {b[k]}")
        elif abs(a[k] - b[k]) > EPS:
            out.append(f"    summary.{k}: {a[k]:.2f} -> {b[k]:.2f}  (Δ {b[k] - a[k]:+.2f})")
    return out


def _diff_events(legacy, converged) -> list:
    out = []
    la = {_event_key(e): e for e in legacy.events}
    lb = {_event_key(e): e for e in converged.events}
    for k in sorted(set(la) | set(lb)):
        ea, eb = la.get(k), lb.get(k)
        if ea is None:
            out.append(f"    + event only in CONVERGED: {k} gain={eb.gain_loss:.2f}")
            continue
        if eb is None:
            out.append(f"    - event only in LEGACY:    {k} gain={ea.gain_loss:.2f}")
            continue
        for f in ("gain_loss", "total_acquisition_cost", "acquisition_fraction", "portfolio_value"):
            va, vb = float(getattr(ea, f)), float(getattr(eb, f))
            if abs(va - vb) > EPS:
                out.append(f"    ~ {k[1]} {k[2]} {f}: {va:.2f} -> {vb:.2f}  (Δ {vb - va:+.2f})")
        if ea.holding_period != eb.holding_period:
            out.append(f"    ~ {k[1]} {k[2]} holding_period: {ea.holding_period} -> {eb.holding_period}")
    return out


async def main(years: list[int]) -> int:
    engine = create_async_engine(_env_database_url(), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    svc = ReportService()

    users_with_changes = 0
    total_changed_cells = 0

    async with session_factory() as db:
        user_ids = [str(u) for u in (await db.execute(select(User.id))).scalars().all()]

    print(f"Shadow 2086 — {len(user_ids)} users × years {years}\n")

    for uid in user_ids:
        for year in years:
            # Fresh session per computation so no state bleeds between modes.
            async with session_factory() as db:
                legacy = await svc.compute_tax_2086(db, uid, year, mode=report_service.TAX_MODE_LEGACY)
            async with session_factory() as db:
                converged = await svc.compute_tax_2086(db, uid, year)

            diffs = _diff_summary(legacy, converged) + _diff_events(legacy, converged)
            if diffs:
                users_with_changes += 1
                total_changed_cells += len(diffs)
                print(f"user={uid} year={year}")
                print("\n".join(diffs))
                print()

    await engine.dispose()

    print("─" * 60)
    if total_changed_cells == 0:
        print("No differences — the convergence changes nothing on this dataset.")
    else:
        print(f"{total_changed_cells} changed figures across {users_with_changes} (user, year) pairs.")
        print("Review each line above before trusting the converged 2086 in prod.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shadow-compare legacy vs converged 2086 tax.")
    parser.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.years)))
