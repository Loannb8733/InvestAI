"""Add internal_hash column to transactions for deduplication.

Revision ID: 031_transaction_internal_hash
Revises: 030_crowdfunding_repayments
"""

from alembic import op
import sqlalchemy as sa

revision = "031_transaction_internal_hash"
down_revision = "030_crowdfunding_repayments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("internal_hash", sa.String(40), nullable=True))
    op.create_index("ix_transactions_internal_hash", "transactions", ["internal_hash"])
    # Unique partial index: only enforce uniqueness where hash is set
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_internal_hash "
        "ON transactions (internal_hash) "
        "WHERE internal_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_transactions_internal_hash")
    op.drop_index("ix_transactions_internal_hash", table_name="transactions")
    op.drop_column("transactions", "internal_hash")
