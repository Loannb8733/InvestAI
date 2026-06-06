"""Fixe la derniere transaction OM (Mantra Chain) price=0.

Plan A (CoinGecko) echoue: ``mantra-dao`` et ``mantra`` renvoient 401.
Plan B (sibling KAITO via CoinGecko) echoue aussi (401).
Plan C (ici): Yahoo Finance ``OM-USD`` -> Close du jour -> conversion
EUR via ``fx_daily_rates``.

Verifie: OM-USD existe bien sur Yahoo (open 7.62 USD, close 7.15 USD au
2025-03-03). On prend Close.

Dry-run par defaut, --apply pour ecrire. Idempotent (skip si price != 0).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from decimal import Decimal

import yfinance as yf
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


def fetch_om_usd_close(day: date) -> Decimal:
    end = day.replace(day=day.day + 1) if day.day < 28 else None
    # yfinance veut une fenetre. Prendre J et J+1 pour etre safe.
    start = day.strftime("%Y-%m-%d")
    end_str = day.toordinal() + 2
    from datetime import date as _date

    end_date = _date.fromordinal(end_str).strftime("%Y-%m-%d")
    hist = yf.Ticker("OM-USD").history(start=start, end=end_date)
    if hist.empty:
        raise RuntimeError(f"Yahoo OM-USD vide pour {day}")
    # Prendre la ligne du jour exact (premiere ligne).
    close = Decimal(str(hist.iloc[0]["Close"]))
    return close


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    async with eng.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT t.id::text AS tx_id, t.quantity AS qty,"
                        " t.executed_at, t.external_id"
                        " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                        " WHERE a.symbol = 'OM'"
                        "   AND (t.price = 0 OR t.price IS NULL)"
                        "   AND t.external_id LIKE 'convert_%'"
                        " ORDER BY t.executed_at LIMIT 1"
                    )
                )
            )
            .mappings()
            .first()
        )
        if not row:
            print("Pas de OM avec price=0. Rien a faire.")
            return 0

        day = row["executed_at"].date()
        qty = D(row["qty"])
        tx_id = row["tx_id"]
        print(f"OM tx={tx_id[:8]} qty={qty} executed={day}")

        # 1) prix USD via Yahoo
        price_usd = fetch_om_usd_close(day)
        print(f"OM-USD close @ {day}: {price_usd} USD")

        # 2) taux USD->EUR via fx_daily_rates
        fx_row = (
            await conn.execute(
                text(
                    "SELECT rate FROM fx_daily_rates"
                    " WHERE base_currency = 'USD' AND quote_currency = 'EUR'"
                    "   AND rate_date = :d LIMIT 1"
                ),
                {"d": day},
            )
        ).first()
        if not fx_row:
            print(f"Pas de fx USD->EUR pour {day}.")
            return 1
        usd_eur = D(fx_row[0])
        price_eur = price_usd * usd_eur
        print(f"USD->EUR @ {day}: {usd_eur}")
        print(f"=> price OM = {float(price_eur):.6f} EUR/OM")
        print(f"   total EUR conversion = {float(price_eur * qty):.4f}")

        if not args.apply:
            print("\nDry-run. Re-run avec --apply.")
            return 0

        async with eng.begin() as tx_conn:
            await tx_conn.execute(
                text("UPDATE transactions SET price = :px WHERE id = :tid"),
                {"px": price_eur, "tid": tx_id},
            )
        print(f"\nApplique. tx_id={tx_id}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
