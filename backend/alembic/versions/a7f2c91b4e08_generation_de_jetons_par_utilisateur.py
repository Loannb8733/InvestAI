"""Génération de jetons par utilisateur (NEW-65)

La révocation se faisait jeton par jeton, à la déconnexion : rien ne rattachait
un jeton déjà émis au mot de passe qui l'avait produit. Un jeton de
rafraîchissement dérobé restait donc valable **sept jours** après que la victime
a changé son mot de passe — alors que c'est précisément le geste par lequel on
reprend la main sur un compte compromis.

Chaque jeton porte désormais la génération qui l'a vu naître ; un changement de
mot de passe incrémente celle de l'utilisateur et périme tout ce qui précède.

Un compteur plutôt qu'un horodatage : la date d'émission d'un JWT se compte en
secondes, si bien qu'un jeton émis dans la même seconde que le changement serait
accepté — et que le jeton neuf rendu à la session courante risquerait, lui,
d'être refusé.

La valeur par défaut est **zéro**, celle qu'un jeton sans génération vaut
implicitement : le déploiement ne déconnecte personne.

Écrite à la main plutôt qu'autogénérée : `alembic revision --autogenerate`
propose sur ce schéma la suppression de `price_history` et d'une vingtaine
d'index, que le modèle ne déclare pas mais que la base porte (voir
cc8154d9307f, qui a rencontré le même écueil).

Revision ID: a7f2c91b4e08
Revises: cc8154d9307f
Create Date: 2026-09-10
"""

import sqlalchemy as sa

from alembic import op

revision = "a7f2c91b4e08"
down_revision = "cc8154d9307f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
