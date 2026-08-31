"""Le schéma déclaré et la migration d'alignement ne doivent plus diverger.

Deux divergences constatées le 2026-08-31 entre dev et prod, chacune en retard sur
l'autre pour un objet différent :

- ``prediction_logs.price_at_creation`` : déclarée au modèle, présente en prod,
  absente en dev — un export `SELECT *` échouait à l'import ;
- la FK ``transactions.related_transaction_id`` : ``ondelete="SET NULL"`` au modèle
  et en dev, mais NO ACTION en prod — y supprimer une transaction référencée levait
  une violation de contrainte au lieu de délier la référence.

Conséquence de fond : ce qui est validé en dev ne garantit rien en prod, ce qui
sape la méthode « tester sur une copie avant d'écrire en production ».

Ces tests lisent le modèle et la migration : ils n'ont besoin d'aucune base.
"""

from pathlib import Path

from app.models.prediction_log import PredictionLog
from app.models.transaction import Transaction

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "s0n1o2p3q4r5_align_dev_prod_schema.py"
).read_text(encoding="utf-8")


class TestModele:
    def test_price_at_creation_est_declaree(self):
        assert "price_at_creation" in PredictionLog.__table__.columns

    def test_la_fk_delie_au_lieu_de_bloquer(self):
        fks = [fk for fk in Transaction.__table__.foreign_keys if fk.parent.name == "related_transaction_id"]
        assert fks, "clé étrangère related_transaction_id absente du modèle"
        assert fks[0].ondelete == "SET NULL", (
            "sans SET NULL, supprimer une transaction référencée lève une violation "
            "de contrainte au lieu de délier la référence"
        )


class TestMigration:
    def test_la_colonne_est_ajoutee_sans_echouer_si_presente(self):
        # Les deux bases divergent en sens opposés : la migration doit passer partout.
        assert "ADD COLUMN IF NOT EXISTS price_at_creation" in _MIGRATION

    def test_la_fk_est_recreee_seulement_si_son_comportement_differe(self):
        # 'n' = SET NULL dans pg_constraint.confdeltype ; on ne prend un verrou que
        # sur une base réellement non conforme.
        assert "confdeltype" in _MIGRATION
        assert "ON DELETE SET NULL" in _MIGRATION
        assert "actuel <> 'n'" in _MIGRATION

    def test_elle_gere_la_contrainte_absente(self):
        assert "IF actuel IS NULL THEN" in _MIGRATION

    def test_le_downgrade_ne_defait_rien(self):
        # Retirer ces objets remettrait la base en divergence avec le code qui
        # l'interroge — et la colonne contient des données en production.
        bloc = _MIGRATION.split("def downgrade()")[-1]
        for destructeur in ("DROP COLUMN", "DROP CONSTRAINT"):
            assert destructeur not in bloc, f"downgrade ne doit pas contenir {destructeur}"
