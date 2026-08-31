"""Aligner les schémas dev et prod sur le modèle SQLAlchemy

Deux divergences constatées le 2026-08-31 en comparant les deux bases, chacune en
retard sur l'autre pour un objet différent :

- ``prediction_logs.price_at_creation`` est déclarée dans le modèle et présente en
  prod, mais absente en dev. Un ``SELECT *`` d'export échouait donc à l'import.
- La clé étrangère ``transactions.related_transaction_id`` porte ``ondelete="SET NULL"``
  dans le modèle et l'a en dev, mais pas en prod : y supprimer une transaction
  référencée levait une violation de contrainte au lieu de délier la référence.

Conséquence de fond : ce qui est validé en dev ne garantit rien en prod. Toute la
méthode « tester sur une copie avant d'écrire en production » repose sur l'hypothèse
que les deux schémas se ressemblent — elle était fausse.

Cette migration est écrite pour être IDEMPOTENTE et applicable dans les deux sens :
chaque opération vérifie l'état réel avant d'agir, donc elle ne fait rien là où
l'objet est déjà conforme.

Revision ID: s0n1o2p3q4r5
Revises: r9m0n1o2p3q4
Create Date: 2026-09-01

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s0n1o2p3q4r5"
down_revision: Union[str, None] = "r9m0n1o2p3q4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = "transactions_related_transaction_id_fkey"


def upgrade() -> None:
    # 1. La colonne manquante en dev. IF NOT EXISTS : sans effet là où elle existe.
    op.execute("ALTER TABLE prediction_logs ADD COLUMN IF NOT EXISTS price_at_creation NUMERIC(18, 8)")

    # 2. La contrainte sans ON DELETE SET NULL en prod. On ne la recrée que si son
    #    comportement diffère de la cible ('n' = SET NULL dans pg_constraint), pour
    #    ne pas prendre un verrou inutile sur une base déjà conforme.
    op.execute(
        f"""
        DO $$
        DECLARE actuel "char";
        BEGIN
            SELECT confdeltype INTO actuel
            FROM pg_constraint
            WHERE conname = '{_FK}' AND conrelid = 'transactions'::regclass;

            IF actuel IS NULL THEN
                ALTER TABLE transactions
                    ADD CONSTRAINT {_FK}
                    FOREIGN KEY (related_transaction_id)
                    REFERENCES transactions(id) ON DELETE SET NULL;
            ELSIF actuel <> 'n' THEN
                ALTER TABLE transactions DROP CONSTRAINT {_FK};
                ALTER TABLE transactions
                    ADD CONSTRAINT {_FK}
                    FOREIGN KEY (related_transaction_id)
                    REFERENCES transactions(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Pas de retour en arrière : ces deux objets sont ceux que le modèle déclare.
    # Les retirer remettrait une base en divergence avec le code qui l'interroge —
    # et la colonne contient des données en production.
    pass
