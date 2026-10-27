"""alert armed

Revision ID: 3c9e1f7a2b8d
Revises: f7a2c9d1e3b4
Create Date: 2026-10-27 12:00:00.000000

Une alerte se déclenchait à chaque vérification tant que sa condition restait
vraie, le délai de cinq minutes valant la fréquence de la tâche. ``armed`` passe
à faux au déclenchement et redevient vrai quand la condition est évaluée fausse.
Les alertes existantes partent armées.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3c9e1f7a2b8d"
down_revision: str | None = "f7a2c9d1e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("armed", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("alerts", "armed")
