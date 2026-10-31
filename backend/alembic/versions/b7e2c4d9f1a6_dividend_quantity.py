"""dividend quantity

Revision ID: b7e2c4d9f1a6
Revises: a1d4f7c2e9b3
Create Date: 2026-10-31 18:00:00.000000

Un dividende est un revenu en numéraire : il n'ajoute aucune part. Son enregistrement augmentait pourtant la
quantité de la ligne, sans que le rejeu des coûts le voie. La quantité ajoutée par les dividendes passés est retirée.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e2c4d9f1a6"
down_revision: str | None = "a1d4f7c2e9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVE_DIVIDEND_QUANTITY = """
    UPDATE assets
    SET quantity = GREATEST(assets.quantity - paid.quantity, 0)
    FROM (
        SELECT asset_id, SUM(quantity) AS quantity
        FROM transactions
        WHERE transaction_type::text = 'DIVIDEND'
        GROUP BY asset_id
    ) AS paid
    WHERE assets.id = paid.asset_id
"""


def upgrade() -> None:
    op.execute(REMOVE_DIVIDEND_QUANTITY)


def downgrade() -> None:
    pass
