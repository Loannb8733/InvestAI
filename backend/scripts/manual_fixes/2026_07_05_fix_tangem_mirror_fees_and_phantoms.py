"""Corrige les quantités Tangem : frais double-déduits + mirrors fantômes.

Contexte (diagnostic 2026-07-05, écarts InvestAI vs Tangem réel) :

1. BUG frais double-déduits — les mirrors TRANSFER_IN du 2026-06-28
   (retraits Binance → Tangem) ont enregistré ``amount − fee`` alors que
   l'``amount`` de l'API Binance est DÉJÀ le net reçu on-chain (frais prélevés
   en plus). Corrigé dans le code (transfer_service.amount_is_net) ; ce script
   répare les 4 lignes historiques → quantité = montant du TRANSFER_OUT source.

2. Mirrors FANTÔMES — des TRANSFER_OUT de pure comptabilité (purge de soldes
   fantômes Kraken du 07/06, « Ajustement balance Kraken » du 05/06) ont été
   auto-mirrorés comme de vrais dépôts Tangem alors qu'aucun coin n'a bougé
   on-chain. Corrigé dans le code (filtre withdrawal_% dans api_keys) ; ce
   script supprime les 4 faux dépôts.

3. Recalcule quantity + avg_buy_price des assets Tangem depuis leurs
   transactions (répare aussi l'écrasement du 28/06).

Vérification finale : les soldes recalculés doivent égaler EXACTEMENT les
soldes Tangem observés par l'utilisateur — sinon ROLLBACK intégral.

Usage :
    DATABASE_URL=postgresql://... python -m scripts.manual_fixes.2026_07_05_fix_tangem_mirror_fees_and_phantoms          # dry-run
    DATABASE_URL=postgresql://... python -m scripts.manual_fixes.2026_07_05_fix_tangem_mirror_fees_and_phantoms --apply  # écrit
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

APPLY = "--apply" in sys.argv


def _ts(s: str) -> datetime:
    """'2026-06-28 21:33:12+00' -> datetime tz-aware (asyncpg exige un datetime)."""
    return datetime.fromisoformat(s.replace("+00", "+00:00"))


# (symbol, executed_at, ancienne qty, nouvelle qty = net réellement reçu)
FEE_FIXES = [
    ("ETH", "2026-06-28 21:33:12+00", Decimal("0.165194850000"), Decimal("0.165294850000")),
    ("SOL", "2026-06-28 21:36:27+00", Decimal("2.998264630000"), Decimal("2.999264630000")),
    ("TAO", "2026-06-28 21:39:11+00", Decimal("0.034293480000"), Decimal("0.034693480000")),
    ("USDC", "2026-06-28 21:46:43+00", Decimal("56.432449000000"), Decimal("57.032449000000")),
]

# (symbol, executed_at, qty) — faux dépôts Tangem issus de purges/ajustements
PHANTOM_MIRRORS = [
    ("ETH", "2026-06-07 23:19:43.593236+00", Decimal("0.001294822400")),
    ("SOL", "2026-06-07 23:19:43.593236+00", Decimal("0.017595502400")),
    ("USDC", "2026-06-07 23:19:43.593236+00", Decimal("0.306200000000")),
    ("USDC", "2026-06-05 13:56:28.931281+00", Decimal("34.800004000000")),
]

# Soldes Tangem réels (source: app Tangem de l'utilisateur, 2026-07-05)
EXPECTED = {
    "ETH": Decimal("0.17446189"),
    "SOL": Decimal("2.99926463"),
    "TAO": Decimal("0.03469348"),
    "USDC": Decimal("57.032449"),
}

IN_TYPES = ("BUY", "TRANSFER_IN", "CONVERSION_IN", "AIRDROP", "STAKING_REWARD")
OUT_TYPES = ("SELL", "TRANSFER_OUT", "CONVERSION_OUT")


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> int:
    engine = create_async_engine(_url(), echo=False)
    ok = True
    async with engine.begin() as conn:  # une seule transaction — tout ou rien
        # ── 1. Corriger les 4 mirrors du 28/06 (net réellement reçu) ──
        for sym, ts, old_qty, new_qty in FEE_FIXES:
            res = await conn.execute(
                text(
                    """
                UPDATE transactions t SET quantity = :new_qty
                FROM assets a
                WHERE t.asset_id = a.id AND a.symbol = :sym AND a.exchange = 'Tangem'
                  AND t.transaction_type = 'TRANSFER_IN'
                  AND t.executed_at = :ts
                  AND t.quantity = :old_qty
                """
                ),
                {"sym": sym, "ts": _ts(ts), "old_qty": old_qty, "new_qty": new_qty},
            )
            print(f"[fee-fix] {sym}: {old_qty} -> {new_qty}  (rows={res.rowcount})")
            if res.rowcount != 1:
                print(f"  !! attendu 1 ligne, trouvé {res.rowcount} — ABORT")
                ok = False

        # ── 2. Supprimer les 4 mirrors fantômes (aucun mouvement on-chain) ──
        for sym, ts, qty in PHANTOM_MIRRORS:
            # D'abord délier les éventuelles références (OUT source → mirror)
            await conn.execute(
                text(
                    """
                UPDATE transactions SET related_transaction_id = NULL
                WHERE related_transaction_id IN (
                    SELECT t.id FROM transactions t
                    JOIN assets a ON a.id = t.asset_id
                    WHERE a.symbol = :sym AND a.exchange = 'Tangem'
                      AND t.transaction_type = 'TRANSFER_IN'
                      AND t.executed_at = :ts
                      AND t.quantity = :qty
                )
                """
                ),
                {"sym": sym, "ts": _ts(ts), "qty": qty},
            )
            res = await conn.execute(
                text(
                    """
                DELETE FROM transactions t
                USING assets a
                WHERE t.asset_id = a.id AND a.symbol = :sym AND a.exchange = 'Tangem'
                  AND t.transaction_type = 'TRANSFER_IN'
                  AND t.executed_at = :ts
                  AND t.quantity = :qty
                """
                ),
                {"sym": sym, "ts": _ts(ts), "qty": qty},
            )
            print(f"[phantom] {sym} {ts} qty={qty}  (deleted={res.rowcount})")
            if res.rowcount != 1:
                print(f"  !! attendu 1 ligne, trouvé {res.rowcount} — ABORT")
                ok = False

        # ── 3. Recalculer quantity + avg_buy_price depuis les transactions ──
        for sym, expected in EXPECTED.items():
            row = (
                await conn.execute(
                    text(
                        """
                SELECT
                  COALESCE(SUM(CASE WHEN t.transaction_type = ANY(:ins) THEN t.quantity
                                    WHEN t.transaction_type = ANY(:outs) THEN -t.quantity
                                    ELSE 0 END), 0) AS qty,
                  COALESCE(SUM(CASE WHEN t.transaction_type = ANY(:ins) AND t.price > 0
                                    THEN t.quantity * t.price ELSE 0 END), 0) AS cost,
                  COALESCE(SUM(CASE WHEN t.transaction_type = ANY(:ins) AND t.price > 0
                                    THEN t.quantity ELSE 0 END), 0) AS priced_qty
                FROM transactions t JOIN assets a ON a.id = t.asset_id
                WHERE a.symbol = :sym AND a.exchange = 'Tangem'
                """
                    ),
                    {"sym": sym, "ins": list(IN_TYPES), "outs": list(OUT_TYPES)},
                )
            ).one()
            new_qty = Decimal(row.qty)
            new_avg = (Decimal(row.cost) / Decimal(row.priced_qty)) if Decimal(row.priced_qty) > 0 else Decimal("0")
            match = "OK" if new_qty == expected else f"MISMATCH (attendu {expected})"
            print(f"[recalc] {sym}: qty={new_qty} avg={new_avg:.8f}  vs Tangem -> {match}")
            if new_qty != expected:
                ok = False
            await conn.execute(
                text(
                    """
                UPDATE assets SET quantity = :q, avg_buy_price = :avg
                WHERE symbol = :sym AND exchange = 'Tangem'
                """
                ),
                {"q": new_qty, "avg": new_avg, "sym": sym},
            )

        if not ok:
            print("\n>>> Vérifications KO — ROLLBACK intégral.")
            raise SystemExit(2)
        if not APPLY:
            print("\n>>> DRY-RUN (pas de --apply) — ROLLBACK volontaire. Tout est vérifié OK.")
            raise SystemExit(0)
        print("\n>>> APPLY — COMMIT.")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SystemExit:
        raise
