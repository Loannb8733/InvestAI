"""Add email verification fields

Revision ID: 5e79ca77dcc3
Revises: 006_hard_delete_cascade
Create Date: 2026-02-08 17:29:26.007941

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5e79ca77dcc3'
down_revision: Union[str, None] = '006_hard_delete_cascade'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email verification fields to users table
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('email_verification_token', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('email_verification_expires', sa.String(length=30), nullable=True))

    # Set existing users as verified (they were created before this feature)
    op.execute("UPDATE users SET email_verified = true WHERE email_verified IS NULL")

    # Now make email_verified not nullable with default false
    op.alter_column('users', 'email_verified', nullable=False, server_default='false')


def downgrade() -> None:
    op.drop_column('users', 'email_verification_expires')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'email_verified')
