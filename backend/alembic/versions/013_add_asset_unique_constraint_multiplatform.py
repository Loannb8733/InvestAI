"""Add unique constraint for multi-platform asset support.

Allow the same symbol on different exchanges within the same portfolio.
Adds composite unique constraint on (portfolio_id, symbol, exchange).
Backfills NULL exchange values to empty string for existing assets.

Revision ID: 013
Revises: 012
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill NULL exchange to empty string so the unique constraint works
    op.execute("UPDATE assets SET exchange = '' WHERE exchange IS NULL")

    # Make exchange NOT NULL with default empty string
    op.alter_column(
        "assets",
        "exchange",
        existing_type=sa.String(50),
        nullable=False,
        server_default="",
    )

    # Add composite unique constraint
    op.create_unique_constraint(
        "uq_assets_portfolio_symbol_exchange",
        "assets",
        ["portfolio_id", "symbol", "exchange"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_assets_portfolio_symbol_exchange", "assets", type_="unique")

    op.alter_column(
        "assets",
        "exchange",
        existing_type=sa.String(50),
        nullable=True,
        server_default=None,
    )

    # Restore empty strings back to NULL
    op.execute("UPDATE assets SET exchange = NULL WHERE exchange = ''")
