"""Corrige les Convert crypto<->crypto avec price=0 EUR via CoinGecko historique.

Suite logique de ``2026_06_06_convert_zero_price_fix.py`` qui ne traitait que
les cas o\xc3\xb9 le sibling est un stablecoin USD-peg. Ce script va plus loin:

- Cas A: self.symbol est un stablecoin USD (USDC, USDG, USDT...) ->
  price = USD/EUR rate du jour, depuis fx_daily_rates.
- Cas B: self.symbol est un crypto -> prix EUR historique \xc3\xa0 la date
  ``executed_at`` via l'API publique CoinGecko ``/coins/{id}/history``.

Rate-limit CoinGecko free tier: ~30 calls/min. On insere un sleep de 2.5s entre
appels pour rester en dessous. Cache les prix recuperes dans un dict en
memoire (meme symbol + meme date = pas de re-fetch).

Dry-run par defaut, --apply pour ecrire. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

USD_STABLECOINS = frozenset({"USDC", "USDT", "USDG", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD"})

CG_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "PAXG": "pax-gold",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "INJ": "injective-protocol",
    "KAITO": "kaito",
    "LINK": "chainlink",
    "OM": "mantra",
    "ONDO": "ondo-finance",
    "PENDLE": "pendle",
    "PEPE": "pepe",
    "SUI": "sui",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "CGPT": "chatgpt",
}

_PRICE_CACHE: dict[tuple[str, str], Decimal] = {}


def D(v) -> Decimal:
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


async def usd_eur_rate(conn, day: date):
    rate = (
        await conn.execute(
            text(
                "SELECT rate FROM fx_daily_rates "
                "WHERE base_currency='USD' AND quote_currency='EUR' AND rate_date <= :d "
                "ORDER BY rate_date DESC LIMIT 1"
            ),
            {"d": day},
        )
    ).scalar()
    return Decimal(str(rate)) if rate is not None else None


async def coingecko_price(symbol: str, day: date, client: httpx.AsyncClient):
    key = (symbol, day.isoformat())
    if key in _PRICE_CACHE:
        return _PRICE_CACHE[key]
    cg_id = CG_IDS.get(symbol)
    if cg_id is None:
        return None
    cg_date = day.strftime("%d-%m-%Y")
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/history"
    try:
        resp = await client.get(url, params={"date": cg_date, "localization": "false"}, timeout=30.0)
        if resp.status_code == 429:
            await asyncio.sleep(30)
            resp = await client.get(url, params={"date": cg_date, "localization": "false"}, timeout=30.0)
        resp.raise_for_status()
        eur = (((resp.json() or {}).get("market_data") or {}).get("current_price") or {}).get("eur")
        if eur is None:
            return None
        price = Decimal(str(eur))
        _PRICE_CACHE[key] = price
        return price
    except Exception as e:  # noqa: BLE001
        print(f"  ! CoinGecko {symbol} {cg_date}: {type(e).__name__}")
        return None
    finally:
        time.sleep(2.5)


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    eng = create_async_engine(_database_url(), echo=False)
    updates: list[dict] = []
    skips: list[tuple[str, str, str]] = []

    async with httpx.AsyncClient() as client:
        async with eng.connect() as conn:
            zeros = (
                (
                    await conn.execute(
                        text(
                            """
                SELECT t.id::text AS tx_id, a.symbol, a.exchange,
                       t.transaction_type::text AS ttype,
                       t.quantity, t.executed_at
                FROM transactions t JOIN assets a ON a.id = t.asset_id
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
                print("Aucune transaction convert_* avec price=0. Rien a faire.")
                return 0

            for r in zeros:
                tx_id, sym, ts = r["tx_id"], r["symbol"], r["executed_at"]
                qty = D(r["quantity"])
                if qty <= 0 or ts is None:
                    skips.append((tx_id, sym, "qty<=0 or no executed_at"))
                    continue
                day = ts.date()
                if sym in USD_STABLECOINS:
                    rate = await usd_eur_rate(conn, day)
                    if rate is None:
                        skips.append((tx_id, sym, "no USD->EUR rate"))
                        continue
                    new_price, src = rate, f"USD/EUR rate {day}"
                else:
                    price_eur = await coingecko_price(sym, day, client)
                    if price_eur is None or price_eur <= 0:
                        skips.append((tx_id, sym, f"no CoinGecko price (id={CG_IDS.get(sym, '?')})"))
                        continue
                    new_price, src = price_eur, f"CoinGecko {sym} @ {day}"
                updates.append(
                    {
                        "tx_id": tx_id,
                        "new_price": new_price,
                        "qty": qty,
                        "eur_total": qty * new_price,
                        "symbol": sym,
                        "exchange": r["exchange"],
                        "ts": ts,
                        "type": r["ttype"],
                        "src": src,
                    }
                )

    print(f"\n=== {len(updates)} updates calcules ({len(skips)} skips) ===\n")
    for u in updates:
        print(
            f"  {str(u['ts'])[:10]:12} {u['exchange'][:10]:10} {u['symbol']:6} {u['type']:14} qty={float(u['qty']):>14.6f} px={float(u['new_price']):>14.6f} eur={float(u['eur_total']):>10.2f}  {u['src']}"
        )
    for tid, sym, reason in skips:
        print(f"  SKIP tx={tid[:8]} symbol={sym} -> {reason}")

    if not args.apply:
        print("\nDry-run: rien ecrit. Re-run avec --apply.")
        return 0

    async with create_async_engine(_database_url(), echo=False).begin() as tx_conn:
        for u in updates:
            await tx_conn.execute(
                text("UPDATE transactions SET price = :px WHERE id = :tid"), {"px": u["new_price"], "tid": u["tx_id"]}
            )
    print(f"\nApplique : {len(updates)} UPDATE(s) committed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
