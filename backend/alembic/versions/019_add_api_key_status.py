"""Add status enum field to api_keys table.

Revision ID: 019_api_key_status
Revises: 018_unique_external_id_per_asset
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "019_api_key_status"
down_revision: Union[str, None] = "018_unique_external_id_per_asset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL to avoid SQLAlchemy enum casing issues
    op.execute("DROP TYPE IF EXISTS apikeystatus CASCADE")
    op.execute(
        "CREATE TYPE apikeystatus AS ENUM "
        "('active', 'expired', 'rate_limited', 'error')"
    )
    op.execute(
        "ALTER TABLE api_keys "
        "ADD COLUMN status apikeystatus NOT NULL DEFAULT 'active'"
    )
    op.execute(
        "ALTER TABLE api_keys "
        "ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.drop_column("api_keys", "error_count")
    op.drop_column("api_keys", "status")
    op.execute("DROP TYPE IF EXISTS apikeystatus")
