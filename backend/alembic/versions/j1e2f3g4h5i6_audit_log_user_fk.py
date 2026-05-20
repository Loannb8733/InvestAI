"""audit_log_user_fk

Add a nullable FK from audit_logs.user_id → users.id (ON DELETE SET NULL)
to enforce referential integrity while preserving logs after user deletion.

Revision ID: j1e2f3g4h5i6
Revises: i0d1e2f3g4h5
Create Date: 2026-05-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j1e2f3g4h5i6"
down_revision: Union[str, Sequence[str]] = "i0d1e2f3g4h5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_audit_logs_user_id",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_logs_user_id", "audit_logs", type_="foreignkey")
