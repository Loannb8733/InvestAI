"""Réconcilie les ENTRÉES manquantes de l'historique (écart solde/transactions).

Problème
--------
La synchronisation ne remonte qu'une fenêtre limitée de l'historique d'un exchange
(500 trades). Les opérations plus anciennes n'ont jamais été importées, alors que
``asset.quantity`` reflète, lui, le solde réel renvoyé par l'API. L'historique
sous-estime donc la position : sa somme signée peut même devenir négative, ce qui
est impossible pour un stock et prouve à soi seul l'incomplétude.

Ce script matérialise l'entrée manquante par un ``TRANSFER_IN`` explicite, pour que
l'historique redevienne cohérent avec le solde — sans jamais toucher au solde, qui
fait autorité.

Périmètre (volontairement étroit)
---------------------------------
UNIQUEMENT les actifs dont l'historique est INFÉRIEUR au solde (entrée manquante).

Les écarts inverses — historique supérieur au solde, typiques d'un cold wallet dont
les sorties ne sont pas récupérables — ne sont PAS traités : leur nature (cession ou
transfert) change le P&L réalisé, et seule une personne peut la trancher.

Valorisation
------------
Au ``avg_buy_price`` de l'actif : l'entrée ne dilue pas le prix de revient et ne
fabrique aucune plus-value. Un actif au PRU nul est ignoré plutôt que valorisé à
zéro, ce qui créerait une couche à coût zéro et surévaluerait la plus-value latente
(cf. FIN-03).

Idempotence
-----------
Après écriture, l'écart tombe à zéro : un second passage ne propose plus rien.
Dry-run par défaut.

Usage
-----
    python scripts/reconcile_missing_entries.py            # dry-run
    python scripts/reconcile_missing_entries.py --commit   # applique
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.transaction import Transaction, TransactionType  # noqa: E402

_IN = (
    TransactionType.BUY,
    TransactionType.CONVERSION_IN,
    TransactionType.TRANSFER_IN,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.DIVIDEND,
    TransactionType.INTEREST,
)
_OUT = (
    TransactionType.SELL,
    TransactionType.TRANSFER_OUT,
    TransactionType.CONVERSION_OUT,
    TransactionType.FEE,
)

# En dessous, l'écart n'est que du bruit de flottant : on ne crée pas de ligne.
_DUST = Decimal("0.000001")


def history_net(transactions) -> Decimal:
    """Somme signée d'un historique. Fonction pure : testable sans base."""
    total = Decimal("0")
    for tx in transactions:
        qty = Decimal(str(tx.quantity or 0))
        if tx.transaction_type in _IN:
            total += qty
        elif tx.transaction_type in _OUT:
            total -= qty
    return total


def missing_entry(stored: Decimal, history: Decimal, pru: Decimal, dust: Decimal = _DUST):
    """Quantité d'entrée à créer, ou None si la ligne ne doit pas être écrite.

    Renvoie ``(quantite, raison)`` ; ``quantite`` vaut None quand on s'abstient.
    """
    gap = stored - history
    if gap <= dust:
        return None, "historique cohérent, ou écart en sortie (hors périmètre)"
    if pru <= 0:
        return None, "PRU nul : une entrée à coût zéro surévaluerait la plus-value"
    return gap, "entrée antérieure à la fenêtre de synchronisation"


async def reconcile(commit: bool) -> int:
    async with AsyncSessionLocal() as db:
        assets = (await db.execute(select(Asset).where(Asset.asset_type != "CROWDFUNDING"))).scalars().all()
        created = 0
        skipped = []

        for asset in assets:
            txs = (await db.execute(select(Transaction).where(Transaction.asset_id == asset.id))).scalars().all()
            if not txs:
                continue
            stored = Decimal(str(asset.quantity or 0))
            history = history_net(txs)
            pru = Decimal(str(asset.avg_buy_price or 0))

            qty, reason = missing_entry(stored, history, pru)
            if qty is None:
                if stored - history > _DUST:
                    skipped.append((asset.symbol, asset.exchange, stored - history, reason))
                continue

            print(
                f"  {asset.symbol:<8} {(asset.exchange or '-'):<12} "
                f"historique={history} -> solde={stored}  TRANSFER_IN de {qty} @ {pru}"
            )
            db.add(
                Transaction(
                    asset_id=asset.id,
                    transaction_type=TransactionType.TRANSFER_IN,
                    quantity=qty,
                    price=pru,
                    fee=0,
                    currency="EUR",
                    executed_at=datetime.now(timezone.utc),
                    exchange=asset.exchange,
                    notes=f"Réconciliation : {reason}",
                )
            )
            created += 1

        if skipped:
            print("\n  Ignorés :")
            for sym, exch, gap, reason in skipped:
                print(f"    {sym} ({exch or '-'}) écart={gap} — {reason}")

        print(f"\n--- {created} entrée(s) de réconciliation ---")
        if commit:
            await db.commit()
            print("COMMITTED.")
        else:
            await db.rollback()
            print("DRY-RUN : rien écrit. Relancer avec --commit pour appliquer.")
        return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Réconcilie les entrées manquantes de l'historique.")
    parser.add_argument("--commit", action="store_true", help="Applique (défaut : dry-run).")
    args = parser.parse_args()
    asyncio.run(reconcile(args.commit))


if __name__ == "__main__":
    main()
