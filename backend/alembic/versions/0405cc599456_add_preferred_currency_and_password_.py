"""add preferred_currency and password_reset fields

Revision ID: 0405cc599456
Revises: 005_timescaledb_hypertables
Create Date: 2026-02-01 14:21:05.758282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0405cc599456'
down_revision: Union[str, None] = '005_timescaledb_hypertables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notes', sa.Column('transaction_ids', sa.Text(), nullable=True))
    op.add_column('notes', sa.Column('attachments', sa.Text(), nullable=True))
    op.add_column('notes', sa.Column('sentiment', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('preferred_currency', sa.String(length=10), server_default='EUR', nullable=False))
    op.add_column('users', sa.Column('password_reset_token', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_reset_expires')
    op.drop_column('users', 'password_reset_token')
    op.drop_column('users', 'preferred_currency')
    op.drop_column('notes', 'sentiment')
    op.drop_column('notes', 'attachments')
    op.drop_column('notes', 'transaction_ids')
