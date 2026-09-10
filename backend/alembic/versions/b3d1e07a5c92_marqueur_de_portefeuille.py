"""Marqueur de nature sur les portefeuilles (NEW-68)

Le portefeuille de crowdfunding était reconnu **à son nom** : le serveur
cherchait `name == "Crowdfunding"` à la casse exacte, l'écran l'écartait de la
page Portefeuille par `name.toLowerCase() !== 'crowdfunding'`. Deux règles pour
une même question, et un geste banal — renommer le portefeuille — dispersait les
projets à venir dans un second portefeuille créé par le serveur, tout en faisant
réapparaître les actifs existants dans la page Portefeuille.

La colonne est nullable : un portefeuille ordinaire n'en porte aucune valeur.
Les portefeuilles existants nommés « Crowdfunding » sont marqués au passage, à
la casse près, pour que la reconnaissance ne dépende plus jamais du libellé.

Écrite à la main plutôt qu'autogénérée : `alembic revision --autogenerate`
propose sur ce schéma la suppression de `price_history` et d'une vingtaine
d'index, que le modèle ne déclare pas mais que la base porte (voir cc8154d9307f
et a7f2c91b4e08, qui ont rencontré le même écueil).

Revision ID: b3d1e07a5c92
Revises: a7f2c91b4e08
Create Date: 2026-09-10
"""

import sqlalchemy as sa

from alembic import op

revision = "b3d1e07a5c92"
down_revision = "a7f2c91b4e08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("kind", sa.String(length=30), nullable=True))
    op.create_index("ix_portfolios_kind", "portfolios", ["kind"])
    op.execute("UPDATE portfolios SET kind = 'crowdfunding' WHERE lower(name) = 'crowdfunding'")


def downgrade() -> None:
    op.drop_index("ix_portfolios_kind", table_name="portfolios")
    op.drop_column("portfolios", "kind")
