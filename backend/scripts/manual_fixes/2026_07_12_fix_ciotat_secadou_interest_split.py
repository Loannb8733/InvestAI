"""Corrige le split intérêts/prélèvements des versements LA CIOTAT SECADOU (Tokimo).

Constat (CSV Tokimo 2026-07-11) : les 6 échéances avaient un interest_amount
THÉORIQUE plat (1,28 €, soit 6×1,28 = 7,68 € affiché par InvestAI) et aucun
tax_amount. La réalité : intérêts BRUTS 9,54 € − prélèvements à la source
2,86 € (IR 1,19 + CSG 1,67) = 6,68 € nets. Les dates étaient aussi erronées.

Convention InvestAI : interest_amount = intérêt BRUT (base imposable, « seul
vrai P&L, brut de prélèvements »), tax_amount = IR+CSG retenus à la source,
amount = net reçu = interest − tax (capital = 0 sur cet in fine). Après fix :
« Intérêts encaissés » = 9,54 € brut, rapport fiscal = 2,86 € retenus.

NB : la « commission filleul » (2,00 €, bonus de parrainage) N'EST PAS un
intérêt du projet — non enregistrée ici (Tokimo la fond dans son « 8,72 »).

Chaque cible est identifiée par le net (amount) déjà en base ; les deux
échéances à 1,29 € (int/tax identiques) sont assignées par ordre de date.

Usage :
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_fix_ciotat_secadou_interest_split          # dry-run
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_fix_ciotat_secadou_interest_split --apply  # écrit
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

APPLY = "--apply" in sys.argv

# (net amount en base, date cible, intérêt brut, tax IR+CSG) — depuis le CSV.
TARGETS = [
    (Decimal("0.26"), date(2025, 9, 2), Decimal("0.36"), Decimal("0.10")),
    (Decimal("1.27"), date(2025, 10, 1), Decimal("1.80"), Decimal("0.53")),
    (Decimal("1.31"), date(2025, 11, 6), Decimal("1.86"), Decimal("0.55")),
    (Decimal("1.26"), date(2025, 12, 1), Decimal("1.80"), Decimal("0.54")),
    (Decimal("1.29"), date(2026, 1, 6), Decimal("1.86"), Decimal("0.57")),
    (Decimal("1.29"), date(2026, 2, 5), Decimal("1.86"), Decimal("0.57")),
]
EXPECTED_GROSS = Decimal("9.54")
EXPECTED_TAX = Decimal("2.86")
EXPECTED_NET = Decimal("6.68")


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> int:
    engine = create_async_engine(_url(), echo=False)
    ok = True
    async with engine.begin() as conn:  # une transaction — tout ou rien
        pid = (
            await conn.execute(text("SELECT id FROM crowdfunding_projects WHERE project_name = 'LA CIOTAT SECADOU'"))
        ).scalar_one()

        reps = (
            await conn.execute(
                text(
                    """
            SELECT id, amount, payment_date FROM crowdfunding_repayments
            WHERE project_id = :pid ORDER BY amount, payment_date
            """
                ),
                {"pid": pid},
            )
        ).all()

        # File d'attente des cibles par net, dans l'ordre de date pour les doublons.
        from collections import defaultdict, deque

        by_net: dict = defaultdict(deque)
        for net, dt, gross, tax in sorted(TARGETS, key=lambda t: t[1]):
            by_net[net].append((dt, gross, tax))

        matched = 0
        for rid, amount, cur_date in sorted(reps, key=lambda r: r[2] or date.min):
            net = Decimal(str(amount)).quantize(Decimal("0.01"))
            if not by_net.get(net):
                print(f"  !! aucune cible pour net={net} (rep {rid} @ {cur_date}) — ABORT")
                ok = False
                continue
            dt, gross, tax = by_net[net].popleft()
            await conn.execute(
                text(
                    """
                UPDATE crowdfunding_repayments
                SET payment_date = :dt, interest_amount = :gross, tax_amount = :tax,
                    capital_amount = 0, payment_type = 'INTEREST'
                WHERE id = :rid
                """
                ),
                {"dt": dt, "gross": gross, "tax": tax, "rid": rid},
            )
            print(f"  [fix] net={net}  {cur_date} -> {dt}  interet={gross}  tax={tax}")
            matched += 1

        leftover = sum(len(q) for q in by_net.values())
        if matched != 6 or leftover:
            print(f"  !! matched={matched}, cibles restantes={leftover} — ABORT")
            ok = False

        # Vérification des totaux
        row = (
            await conn.execute(
                text(
                    """
            SELECT COALESCE(SUM(interest_amount),0), COALESCE(SUM(tax_amount),0),
                   COALESCE(SUM(amount),0)
            FROM crowdfunding_repayments WHERE project_id = :pid
            """
                ),
                {"pid": pid},
            )
        ).one()
        g, t, n = Decimal(row[0]), Decimal(row[1]), Decimal(row[2])
        print(f"\n  Σ intérêt brut = {g}  (attendu {EXPECTED_GROSS})")
        print(f"  Σ prélèvements = {t}  (attendu {EXPECTED_TAX})")
        print(f"  Σ net (amount) = {n}  (attendu {EXPECTED_NET})")
        if g != EXPECTED_GROSS or t != EXPECTED_TAX or n != EXPECTED_NET:
            print("  !! totaux inattendus — ABORT")
            ok = False

        if not ok:
            print("\n>>> Vérifications KO — ROLLBACK.")
            raise SystemExit(2)
        if not APPLY:
            print("\n>>> DRY-RUN (pas de --apply) — ROLLBACK volontaire. Tout est vérifié OK.")
            raise SystemExit(0)
        print("\n>>> APPLY — COMMIT.")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
