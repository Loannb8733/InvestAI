"""users.target_allocations — allocation cible persistée

Ajoute la colonne JSONB ``users.target_allocations`` : l'allocation cible par
classe crypto (fractions sommant à 1.0, ex ``{"L1": 0.5, "Stable": 0.2}``).

Avant, les cibles vivaient en dur dans le front (DEFAULT_TARGETS de
RebalancingTab) et se réinitialisaient à chaque visite — impossible de bâtir
le widget d'écart vs cible du dashboard ou une alerte de drift dessus.

Revision ID: o6j7k8l9m0n1
Revises: n5i6j7k8l9m0
Create Date: 2026-07-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o6j7k8l9m0n1"
down_revision: Union[str, Sequence[str]] = "n5i6j7k8l9m0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("target_allocations", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "target_allocations")
