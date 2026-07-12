"""Enregistre le bonus de parrainage Tokimo (2,00 €) sur LA CIOTAT SECADOU.

« Commission filleul » du 02/09/2025 (CSV Tokimo) : un bonus de parrainage,
ni intérêt ni capital. Enregistré comme repayment payment_type=REFERRAL —
compté dans la poche « Parrainage & bonus », exclu des intérêts, du XIRR et
du rapport fiscal des intérêts. Idempotent (vérifie l'absence d'un REFERRAL
existant sur le projet).

Prérequis : l'enum PG paymenttype doit contenir REFERRAL (migration
r9m0n1o2p3q4). Ce script l'ajoute aussi (IF NOT EXISTS) au cas où la
migration n'a pas encore été déployée, dans une transaction séparée
(ALTER TYPE ADD VALUE ne peut pas être suivi d'un usage dans la même tx).

Usage :
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_add_ciotat_referral          # dry-run
    DATABASE_URL=... python -m scripts.manual_fixes.2026_07_12_add_ciotat_referral --apply  # écrit
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

APPLY = "--apply" in sys.argv
REFERRAL_AMOUNT = Decimal("2.00")
REFERRAL_DATE = date(2025, 9, 2)


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL not set")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=require", "ssl=require")


async def main() -> int:
    engine = create_async_engine(_url(), echo=False)

    # 1) S'assurer que l'enum contient REFERRAL — hors transaction (autocommit).
    async with engine.connect() as conn:
        await conn.execute(text("COMMIT"))
        await conn.execute(text("ALTER TYPE paymenttype ADD VALUE IF NOT EXISTS 'REFERRAL'"))

    # 2) Insérer le versement de parrainage (transaction, idempotent).
    async with engine.begin() as conn:
        # user_id via la chaîne asset→portfolio ; fallback sur un versement existant.
        row = (
            await conn.execute(
                text(
                    """
            SELECT p.id, po.user_id
            FROM crowdfunding_projects p
            JOIN assets a ON a.id = p.asset_id
            JOIN portfolios po ON po.id = a.portfolio_id
            WHERE p.project_name = 'LA CIOTAT SECADOU'
            """
                )
            )
        ).one()
        pid, user_id = row[0], row[1]

        existing = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM crowdfunding_repayments "
                    "WHERE project_id = :pid AND payment_type = 'REFERRAL'"
                ),
                {"pid": pid},
            )
        ).scalar_one()
        if existing:
            print(f"  Un versement REFERRAL existe déjà ({existing}) — rien à faire.")
            if not APPLY:
                raise SystemExit(0)
            return 0

        print(f"  [insert] REFERRAL {REFERRAL_AMOUNT} € @ {REFERRAL_DATE} sur LA CIOTAT SECADOU")
        if APPLY:
            await conn.execute(
                text(
                    """
                INSERT INTO crowdfunding_repayments
                    (id, project_id, user_id, payment_date, amount, payment_type,
                     interest_amount, capital_amount, tax_amount, notes, created_at)
                VALUES
                    (:id, :pid, :uid, :dt, :amount, 'REFERRAL', 0, 0, 0,
                     'Commission de parrainage (filleul) — Tokimo', now())
                """
                ),
                {
                    "id": uuid.uuid4(),
                    "pid": pid,
                    "uid": user_id,
                    "dt": REFERRAL_DATE,
                    "amount": REFERRAL_AMOUNT,
                },
            )
            print("\n>>> APPLY — COMMIT.")
        else:
            print("\n>>> DRY-RUN (pas de --apply) — ROLLBACK volontaire.")
            raise SystemExit(0)

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
