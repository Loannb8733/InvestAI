"""Add telegram_chat_id and telegram_enabled to users table.

Revision ID: 020_user_telegram_fields
Revises: 019_api_key_status
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "020_user_telegram_fields"
down_revision: Union[str, None] = "019_api_key_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(100), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_enabled")
    op.drop_column("users", "telegram_chat_id")
