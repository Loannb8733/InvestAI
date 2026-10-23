"""price history: volume column, stock rows refetched in EUR

Revision ID: d5f9a3b4c6e7
Revises: c4e8f1a2b3d5
Create Date: 2026-10-19 23:30:00.000000

Les cours Yahoo des actions et ETF étaient enregistrés dans leur devise de
cotation sous la colonne price_eur. Ces lignes sont supprimées : la tâche de
rafraîchissement les recharge converties en euros.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d5f9a3b4c6e7"
down_revision: str | None = "c4e8f1a2b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE asset_price_history ADD COLUMN IF NOT EXISTS volume NUMERIC(30, 8)")
    op.execute(
        "DELETE FROM asset_price_history WHERE symbol IN "
        "(SELECT UPPER(symbol) FROM assets WHERE asset_type IN ('STOCK', 'ETF')) OR symbol IN ('SPY', 'IWDA.AS')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE asset_price_history DROP COLUMN IF EXISTS volume")
