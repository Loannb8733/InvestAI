"""Add conversion fields to transactions.

Revision ID: 002
Revises: 001
Create Date: 2024-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new transaction types to enum
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'conversion_out'")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'conversion_in'")

    # Add related_transaction_id for linking conversion pairs
    op.add_column(
        'transactions',
        sa.Column(
            'related_transaction_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('transactions.id'),
            nullable=True
        )
    )

    # Add conversion_rate field
    op.add_column(
        'transactions',
        sa.Column(
            'conversion_rate',
            sa.Numeric(18, 12),
            nullable=True
        )
    )

    # Create index for related_transaction_id
    op.create_index(
        op.f('ix_transactions_related_transaction_id'),
        'transactions',
        ['related_transaction_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_related_transaction_id'), table_name='transactions')
    op.drop_column('transactions', 'conversion_rate')
    op.drop_column('transactions', 'related_transaction_id')
    # Note: Cannot easily remove enum values in PostgreSQL
