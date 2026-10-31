"""drop snapshot gain

Revision ID: c8f3a1d5e7b2
Revises: b7e2c4d9f1a6
Create Date: 2026-10-31 21:00:00.000000

Le gain stocké dans un instantané suivait la formule du jour de son écriture, deux formules le même jour : il ne
servait qu'à l'infobulle de la courbe quand les cours manquent. Il disparaît plutôt que de rester faux.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8f3a1d5e7b2"
down_revision: str | None = "b7e2c4d9f1a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS portfolio_snapshots DROP COLUMN IF EXISTS total_gain_loss")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS portfolio_snapshots ADD COLUMN IF NOT EXISTS total_gain_loss NUMERIC(18, 2) NOT NULL DEFAULT 0"
    )
