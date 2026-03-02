"""change_last_sync_at_to_datetime

Revision ID: 8b0d743ab1c3
Revises: 013
Create Date: 2026-02-28 16:40:03.623510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8b0d743ab1c3'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear existing string values before type change to avoid cast errors
    op.execute("UPDATE api_keys SET last_sync_at = NULL WHERE last_sync_at IS NOT NULL")
    op.alter_column('api_keys', 'last_sync_at',
               existing_type=sa.VARCHAR(length=255),
               type_=sa.DateTime(timezone=True),
               existing_nullable=True,
               postgresql_using="last_sync_at::timestamp with time zone")


def downgrade() -> None:
    op.alter_column('api_keys', 'last_sync_at',
               existing_type=sa.DateTime(timezone=True),
               type_=sa.VARCHAR(length=255),
               existing_nullable=True)
