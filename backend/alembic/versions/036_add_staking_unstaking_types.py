"""Add staking, unstaking to TransactionType enum.

Revision ID: 036_add_staking_unstaking_types
Revises: 035_add_delay_months_to_crowdfunding_projects
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "036_add_staking_unstaking_types"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'STAKING'")
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'UNSTAKING'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass
