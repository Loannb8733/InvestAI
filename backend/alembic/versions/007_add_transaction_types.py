"""Add airdrop, conversion_in, conversion_out to TransactionType enum.

Revision ID: 007_add_transaction_types
Revises: 006_hard_delete_cascade
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_add_transaction_types"
down_revision: Union[str, None] = "006_hard_delete_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'AIRDROP'")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'CONVERSION_IN'")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'CONVERSION_OUT'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass
