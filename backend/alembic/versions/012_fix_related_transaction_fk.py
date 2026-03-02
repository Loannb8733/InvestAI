"""Fix related_transaction_id FK to use SET NULL on delete.

Revision ID: 012
Revises: 011
Create Date: 2026-02-24

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("transactions_related_transaction_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "transactions_related_transaction_id_fkey",
        "transactions",
        "transactions",
        ["related_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Also fix portfolio_snapshots FK (should be SET NULL, not CASCADE)
    op.drop_constraint("portfolio_snapshots_portfolio_id_fkey", "portfolio_snapshots", type_="foreignkey")
    op.create_foreign_key(
        "portfolio_snapshots_portfolio_id_fkey",
        "portfolio_snapshots",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("transactions_related_transaction_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "transactions_related_transaction_id_fkey",
        "transactions",
        "transactions",
        ["related_transaction_id"],
        ["id"],
    )

    op.drop_constraint("portfolio_snapshots_portfolio_id_fkey", "portfolio_snapshots", type_="foreignkey")
    op.create_foreign_key(
        "portfolio_snapshots_portfolio_id_fkey",
        "portfolio_snapshots",
        "portfolios",
        ["portfolio_id"],
        ["id"],
    )
