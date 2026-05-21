"""add cash_balances to portfolios

Add the cash_balances JSON column that tracks fiat/stablecoin balances held
on exchanges per portfolio. Was present in the ORM model but never migrated.

Revision ID: k2f3g4h5i6j7
Revises: j1e2f3g4h5i6
Create Date: 2026-05-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "k2f3g4h5i6j7"
down_revision: Union[str, Sequence[str]] = "j1e2f3g4h5i6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: column may already exist if DB was created via create_all
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='portfolios' AND column_name='cash_balances'"
        )
    ).fetchone()
    if result is None:
        op.add_column(
            "portfolios",
            sa.Column(
                "cash_balances",
                JSON,
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    op.drop_column("portfolios", "cash_balances")
