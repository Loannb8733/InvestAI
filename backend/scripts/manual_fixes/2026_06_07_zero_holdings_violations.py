"""Resout 19 holdings violations restantes du watchdog.

Identifie en investigation:

* DOGE/PEPE Kraken: le sync importe les recompenses Kraken en double
  (AIRDROP + STAKING_REWARD pour le meme id Kraken). On supprime les
  doublons AIRDROP en gardant STAKING_REWARD (semantiquement correct).
* USDT Binance: TRANSFER_IN duplique (148.52 USDT @ 2026-05-05 01:12 avec
  ``external_id=NULL`` — vrai depot a 2026-05-04 23:03 avec ext valide).
* 6 TOKIMO CROWDFUNDING: par design ces NFT n'ont pas de transactions
  classiques. Le watchdog devrait les exclure.
* 6 dust + 3 small Kraken: assets.quantity desynchronise de computed
  pour < 5 EUR au total. Snap a computed.

Idempotent (skip si fix deja applique). Dry-run par defaut.

Ne corrige pas:

* USDC Binance: difference de 442 USDC liee a un STAKING transaction
  (468 USDC en Binance Earn). Violation structurelle, sera neutralisee
  cote watchdog (commit suivant exclut STAKING du computed).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
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


async def delete_kraken_airdrop_duplicates(conn, symbol: str, apply: bool) -> int:
    """DELETE AIRDROP rows whose external_id matches a STAKING_REWARD row
    (same Kraken reward id, just different prefix reward_airdrop_ vs reward_staking_)."""
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT a.id::text AS aid, t.id::text AS tid, t.external_id AS ext,"
                    " t.quantity AS qty"
                    " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                    " WHERE a.symbol = :sym AND a.exchange = 'Kraken'"
                    "   AND t.transaction_type = 'AIRDROP'"
                    "   AND t.external_id LIKE 'reward_airdrop_%'"
                ),
                {"sym": symbol},
            )
        )
        .mappings()
        .all()
    )
    n = 0
    for r in rows:
        suffix = r["ext"].removeprefix("reward_airdrop_")
        # Verifier qu'un STAKING_REWARD existe pour le meme suffix et meme qty
        match = (
            await conn.execute(
                text(
                    "SELECT t.id::text FROM transactions t"
                    " WHERE t.asset_id = :aid"
                    "   AND t.transaction_type = 'STAKING_REWARD'"
                    "   AND t.external_id = :ext"
                    "   AND t.quantity = :qty"
                ),
                {
                    "aid": r["aid"],
                    "ext": f"reward_staking_{suffix}",
                    "qty": r["qty"],
                },
            )
        ).first()
        if match:
            print(f"  {symbol} AIRDROP doublon tid={r['tid'][:8]} qty={r['qty']} ext={r['ext']}")
            if apply:
                await conn.execute(
                    text(
                        "UPDATE transactions SET related_transaction_id = NULL" " WHERE related_transaction_id = :tid"
                    ),
                    {"tid": r["tid"]},
                )
                await conn.execute(
                    text("DELETE FROM transactions WHERE id = :tid"),
                    {"tid": r["tid"]},
                )
            n += 1
    return n


async def delete_usdt_transfer_in_duplicate(conn, apply: bool) -> int:
    """USDT Binance TRANSFER_IN qty=148.520300 with external_id=NULL is duplicate
    of the real deposit_5032785806503769345 less than 3h earlier."""
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT t.id::text AS tid, t.quantity AS qty, t.executed_at AS d,"
                    " t.external_id AS ext"
                    " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                    " WHERE a.symbol = 'USDT' AND a.exchange = 'Binance'"
                    "   AND t.transaction_type = 'TRANSFER_IN'"
                    "   AND t.external_id IS NULL"
                    "   AND t.quantity = 148.520300"
                )
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return 0
    for r in rows:
        # Verifier qu'un TRANSFER_IN avec ext valide existe pour la meme qty
        match = (
            await conn.execute(
                text(
                    "SELECT 1 FROM transactions t JOIN assets a ON a.id = t.asset_id"
                    " WHERE a.symbol = 'USDT' AND a.exchange = 'Binance'"
                    "   AND t.transaction_type = 'TRANSFER_IN'"
                    "   AND t.external_id LIKE 'deposit_%'"
                    "   AND t.quantity = 148.520300"
                )
            )
        ).first()
        if not match:
            print(f"  USDT TRANSFER_IN tid={r['tid'][:8]} pas de jumeau ext=deposit_ — skip")
            continue
        print(f"  USDT TRANSFER_IN doublon tid={r['tid'][:8]} qty={r['qty']} date={r['d']}")
        if apply:
            # Detacher d'eventuelles references related_transaction_id
            await conn.execute(
                text("UPDATE transactions SET related_transaction_id = NULL" " WHERE related_transaction_id = :tid"),
                {"tid": r["tid"]},
            )
            await conn.execute(
                text("DELETE FROM transactions WHERE id = :tid"),
                {"tid": r["tid"]},
            )
    return len(rows)


async def snap_dust_holdings(conn, apply: bool) -> int:
    """Pour chaque asset non-CROWDFUNDING avec diff < 5 EUR, set quantity = computed."""
    THRESHOLD_EUR = Decimal("5")
    STABLES = {"USDC", "USDT", "USDG", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD"}
    prices = {
        r[0]: D(r[1])
        for r in (
            await conn.execute(
                text(
                    "SELECT DISTINCT ON (symbol) symbol, price_eur FROM asset_price_history"
                    " ORDER BY symbol, price_date DESC"
                )
            )
        ).all()
    }
    rows = (
        (
            await conn.execute(
                text(
                    "SELECT a.id::text AS aid, a.symbol, a.exchange,"
                    " a.quantity AS stored, a.asset_type::text AS at FROM assets a"
                    " WHERE a.asset_type != 'CROWDFUNDING'"
                )
            )
        )
        .mappings()
        .all()
    )
    n = 0
    for r in rows:
        tx_rows = (
            await conn.execute(
                text(
                    "SELECT transaction_type::text AS tt, SUM(quantity) AS q"
                    " FROM transactions WHERE asset_id = :aid GROUP BY transaction_type"
                ),
                {"aid": r["aid"]},
            )
        ).all()
        sums = {tt: D(q) for tt, q in tx_rows}
        computed = (
            sums.get("BUY", Decimal(0))
            - sums.get("SELL", Decimal(0))
            + sums.get("CONVERSION_IN", Decimal(0))
            - sums.get("CONVERSION_OUT", Decimal(0))
            + sums.get("TRANSFER_IN", Decimal(0))
            - sums.get("TRANSFER_OUT", Decimal(0))
            + sums.get("AIRDROP", Decimal(0))
            + sums.get("STAKING_REWARD", Decimal(0))
            + sums.get("STAKING", Decimal(0))
        )
        stored = D(r["stored"])
        diff = stored - computed
        if abs(diff) < Decimal("0.00000001"):
            continue
        sym = r["symbol"]
        px = D("0.86") if sym in STABLES else prices.get(sym, Decimal(0))
        diff_eur = abs(diff) * px
        if diff_eur >= THRESHOLD_EUR:
            print(
                f"  {sym:<10} {r['exchange']:<12} diff_eur={float(diff_eur):.2f} >= {THRESHOLD_EUR} — SKIP (pas dust)"
            )
            continue
        print(
            f"  SNAP {sym:<10} {r['exchange']:<12} {float(stored)} -> {float(computed)} "
            f"(diff_eur={float(diff_eur):.2f})"
        )
        if apply:
            await conn.execute(
                text("UPDATE assets SET quantity = :q WHERE id = :aid"),
                {"q": computed, "aid": r["aid"]},
            )
        n += 1
    return n


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    url = _database_url()
    eng = create_async_engine(url, echo=False)

    async with eng.begin() as conn:
        print("=== DOGE Kraken AIRDROP doublons ===")
        n_doge = await delete_kraken_airdrop_duplicates(conn, "DOGE", args.apply)
        print(f"  -> {n_doge} a supprimer\n")
        print("=== PEPE Kraken AIRDROP doublons ===")
        n_pepe = await delete_kraken_airdrop_duplicates(conn, "PEPE", args.apply)
        print(f"  -> {n_pepe} a supprimer\n")
        print("=== USDT Binance TRANSFER_IN doublon ===")
        n_usdt = await delete_usdt_transfer_in_duplicate(conn, args.apply)
        print(f"  -> {n_usdt} a supprimer\n")
        # Snap aprés les suppressions pour recalculer
        print("=== Snap dust holdings (< 5 EUR) ===")
        n_snap = await snap_dust_holdings(conn, args.apply)
        print(f"  -> {n_snap} a snap\n")

    if not args.apply:
        print("Dry-run. Re-run avec --apply.")
    else:
        print("Applique.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
