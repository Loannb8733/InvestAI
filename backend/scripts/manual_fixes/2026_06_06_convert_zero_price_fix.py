"""Corrige les transactions Convert avec price=0 EUR en utilisant les taux FX historiques reels.

Methode raffinee:
  1. Cas FACILE - sibling est stablecoin USD-peg (USDC, USDT, USDG, BUSD, DAI):
       price_self = (qty_sibling * usd_eur_rate_of_the_day) / qty_self
  2. Cas DIFFICILE - sibling est crypto: pour l instant on skip et on liste.
"""

import argparse
import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Stablecoins peg USD (a la decimale pres on les traite comme = 1 USD)
USD_STABLECOINS = frozenset({"USDC", "USDT", "USDG", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD"})


def D(v):
    return Decimal(str(v or 0))


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set.")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    return url


async def get_usd_eur_rate(conn, day):
    """Recupere le taux USD->EUR pour une date donnee (ou plus proche)."""
    rate = (
        await conn.execute(
            text(
                """
        SELECT rate FROM fx_daily_rates
        WHERE base_currency='USD' AND quote_currency='EUR'
          AND rate_date <= :d
        ORDER BY rate_date DESC LIMIT 1
    """
            ),
            {"d": day},
        )
    ).scalar()
    return Decimal(str(rate)) if rate else None


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="actually UPDATE prices (default: dry-run)")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    async with eng.connect() as conn:
        zeros = (
            (
                await conn.execute(
                    text(
                        """
            SELECT t.id::text AS tx_id, a.symbol, a.exchange, t.transaction_type::text AS type,
                   t.quantity, t.executed_at, t.external_id
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE (t.price = 0 OR t.price IS NULL)
              AND t.external_id LIKE 'convert_%'
            ORDER BY t.executed_at NULLS LAST
        """
                    )
                )
            )
            .mappings()
            .all()
        )

        if not zeros:
            print("Aucune transaction convert_* avec price=0.")
            return 0

        easy_updates = []
        hard_cases = []

        for r in zeros:
            tx_id = r["tx_id"]
            ext_self = r["external_id"]
            ts = r["executed_at"]

            if ext_self.startswith("convert_buy_"):
                suffix = ext_self[len("convert_buy_") :]
                sibling_prefix = "convert_sell_"
            elif ext_self.startswith("convert_sell_"):
                suffix = ext_self[len("convert_sell_") :]
                sibling_prefix = "convert_buy_"
            else:
                continue

            sibling = (
                (
                    await conn.execute(
                        text(
                            """
                SELECT t.id::text AS tx_id, a.symbol, t.quantity
                FROM transactions t
                JOIN assets a ON a.id = t.asset_id
                WHERE t.external_id = :sext
            """
                        ),
                        {"sext": f"{sibling_prefix}{suffix}"},
                    )
                )
                .mappings()
                .first()
            )

            if not sibling:
                hard_cases.append((r, None, "pas de sibling"))
                continue

            qty_self = D(r["quantity"])
            qty_sib = D(sibling["quantity"])
            sib_symbol = sibling["symbol"]

            if sib_symbol in USD_STABLECOINS:
                # Cas FACILE: convertir qty_USD via fx_daily_rates
                usd_eur = await get_usd_eur_rate(conn, ts.date())
                if usd_eur is None:
                    hard_cases.append((r, sibling, "no FX rate"))
                    continue
                eur_total = qty_sib * usd_eur  # qty_USDC ~ qty_USD, multiplied by USD_EUR rate
                new_price = eur_total / qty_self if qty_self > 0 else D(0)
                easy_updates.append(
                    {
                        "tx_id": tx_id,
                        "new_price": new_price,
                        "symbol": r["symbol"],
                        "sib": sib_symbol,
                        "ts": ts,
                        "qty_self": qty_self,
                        "qty_sib": qty_sib,
                        "usd_eur": usd_eur,
                        "eur_total": eur_total,
                    }
                )
            else:
                hard_cases.append((r, sibling, "sibling is crypto"))

        # Affichage cas faciles
        print(f"=== CAS FACILES — sibling stablecoin USD ({len(easy_updates)}) ===\n")
        if easy_updates:
            print(
                f"{'DATE':12} {'EX':10} {'SYM':5} {'QTY':>14} {'USDC_qty':>10} {'USD_EUR':>8} {'TOTAL€':>10} {'NEW PRICE':>14}"
            )
            print("-" * 100)
            for u in easy_updates:
                print(
                    f"{str(u['ts'])[:10]:12} {('?'):10} {u['symbol']:5} {float(u['qty_self']):>14.8f} "
                    f"{float(u['qty_sib']):>10.4f} {float(u['usd_eur']):>8.4f} {float(u['eur_total']):>10.2f} {float(u['new_price']):>14.4f}"
                )

        print()
        print(f"=== CAS DIFFICILES — sibling crypto ({len(hard_cases)}) — SKIP pour l instant ===\n")
        for r, sib, reason in hard_cases:
            sib_str = f"{sib['symbol']} qty={float(D(sib['quantity'])):.4f}" if sib else "no sibling"
            print(
                f"  {str(r['executed_at'])[:10]}  {r['symbol']:6} {r['type']:14} qty={float(D(r['quantity'])):>14.4f}  <- {sib_str:30}  [{reason}]"
            )

        print()
        if not args.apply:
            print(f"\n=== Dry-run: {len(easy_updates)} UPDATE(s) en file. Re-run avec --apply. ===")
            return 0

        async with eng.begin() as tx_conn:
            for u in easy_updates:
                await tx_conn.execute(
                    text("UPDATE transactions SET price = :px WHERE id = :tid"),
                    {"px": u["new_price"], "tid": u["tx_id"]},
                )
            print(f"\nApplique : {len(easy_updates)} UPDATE(s) committed.")
    await eng.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
