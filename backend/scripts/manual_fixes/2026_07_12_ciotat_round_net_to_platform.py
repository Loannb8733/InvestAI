"""Aligne le net crédité LA CIOTAT SECADOU sur les montants Tokimo (6,72 €).

Le « Montant net perçu » arithmétique (brut − IR − CSG par ligne) = 6,68 €,
mais Tokimo CRÉDITE au centime supérieur sur 4 échéances (colonne « Montant »
de leur CSV) → 6,72 €, ce que l'utilisateur a réellement sur son compte.

On arrondit donc le `amount` (net crédité) de ces 4 lignes au centime
supérieur pour refléter le crédit réel, et on met project.total_received à
jour. Les intérêts BRUTS (interest_amount = 9,54) et les prélèvements
(tax_amount = 2,86) sont inchangés (base fiscale). Léger écart d'arrondi
plateforme assumé : 9,54 − 2,86 = 6,68 vs 6,72 crédité.

Usage :
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_ciotat_round_net_to_platform          # dry-run
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_ciotat_round_net_to_platform --apply  # écrit
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

# (date, amount actuel net perçu, amount cible crédité Tokimo)
ROUND_UPS = [
    (date(2025, 11, 6), Decimal("1.31"), Decimal("1.32")),
    (date(2025, 12, 1), Decimal("1.26"), Decimal("1.27")),
    (date(2026, 1, 6), Decimal("1.29"), Decimal("1.30")),
    (date(2026, 2, 5), Decimal("1.29"), Decimal("1.30")),
]
EXPECTED_NET = Decimal("6.72")


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
    async with engine.begin() as conn:
        pid = (
            await conn.execute(text("SELECT id FROM crowdfunding_projects WHERE project_name = 'LA CIOTAT SECADOU'"))
        ).scalar_one()

        for dt, cur, tgt in ROUND_UPS:
            res = await conn.execute(
                text(
                    """
                UPDATE crowdfunding_repayments SET amount = :tgt
                WHERE project_id = :pid AND payment_type = 'INTEREST'
                  AND payment_date = :dt AND amount = :cur
                """
                ),
                {"tgt": tgt, "pid": pid, "dt": dt, "cur": cur},
            )
            print(f"  [round-up] {dt}  {cur} -> {tgt}  (rows={res.rowcount})")
            if res.rowcount != 1:
                print(f"  !! attendu 1 ligne, trouvé {res.rowcount} — ABORT")
                ok = False

        net = Decimal(
            (
                await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(amount),0) FROM crowdfunding_repayments "
                        "WHERE project_id = :pid AND payment_type = 'INTEREST'"
                    ),
                    {"pid": pid},
                )
            ).scalar_one()
        )
        print(f"\n  Σ net intérêts crédité = {net}  (attendu {EXPECTED_NET})")
        if net != EXPECTED_NET:
            ok = False

        # total_received du projet aligné sur le net crédité (capital 0 ici).
        await conn.execute(
            text("UPDATE crowdfunding_projects SET total_received = :n WHERE id = :pid"),
            {"n": EXPECTED_NET, "pid": pid},
        )

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
