"""users.tmi_rate / risk_profile / monthly_dca_eur — profil investisseur

Ajoute les trois paramètres financiers qu'un family office configure en
premier, aujourd'hui hardcodés à 3 endroits du front :

- ``tmi_rate`` (Numeric(4,3)) : tranche marginale d'imposition (0, 0.11,
  0.30, 0.41, 0.45) — utilisée par l'estimation d'impôt au barème progressif.
- ``risk_profile`` (String(20)) : conservative / moderate / aggressive —
  utilisé par les suggestions de déploiement de capital.
- ``monthly_dca_eur`` (Numeric(10,2)) : montant DCA mensuel — pré-remplit
  les simulateurs de projection.

Toutes nullables : NULL = non renseigné, le front garde son comportement
actuel (plancher PS 17,2 %, pas de pré-remplissage).

Revision ID: q8l9m0n1o2p3
Revises: p7k8l9m0n1o2
Create Date: 2026-07-11

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q8l9m0n1o2p3"
down_revision: Union[str, None] = "p7k8l9m0n1o2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tmi_rate", sa.Numeric(4, 3), nullable=True))
    op.add_column("users", sa.Column("risk_profile", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("monthly_dca_eur", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "monthly_dca_eur")
    op.drop_column("users", "risk_profile")
    op.drop_column("users", "tmi_rate")
