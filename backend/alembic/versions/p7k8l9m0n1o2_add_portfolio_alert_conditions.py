"""Add portfolio-level alert conditions (drawdown / HHI / allocation drift).

Étend l'enum PG ``alertcondition`` avec 3 conditions au niveau portefeuille
(asset_id NULL) : repli depuis le plus-haut, concentration HHI, dérive vs
allocation cible. Ce sont les alertes qui protègent un patrimoine concentré,
là où les seuils par actif ne voient rien.

Revision ID: p7k8l9m0n1o2
Revises: o6j7k8l9m0n1
Create Date: 2026-07-09

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p7k8l9m0n1o2"
down_revision: Union[str, None] = "o6j7k8l9m0n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy stocke le .name (majuscules) de l'Enum dans PostgreSQL.
    op.execute("ALTER TYPE alertcondition ADD VALUE IF NOT EXISTS 'PORTFOLIO_DRAWDOWN'")
    op.execute("ALTER TYPE alertcondition ADD VALUE IF NOT EXISTS 'CONCENTRATION_HHI'")
    op.execute("ALTER TYPE alertcondition ADD VALUE IF NOT EXISTS 'ALLOCATION_DRIFT'")


def downgrade() -> None:
    # PostgreSQL ne supporte pas la suppression de valeurs d'enum.
    pass
