"""add_composite_indexes

Add composite indexes for P&L calculation queries and audit log lookups:
- transactions(asset_id, transaction_type) — speeds up per-asset P&L aggregation
- audit_logs(resource_type, resource_id) — speeds up audit trail lookups by resource

Revision ID: h9c3d4e5f6g7
Revises: g8b2c3d4e5f6
Create Date: 2026-03-21 23:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h9c3d4e5f6g7"
down_revision: Union[str, Sequence[str]] = ("g8b2c3d4e5f6", "036_add_staking_unstaking_types")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_asset_id_transaction_type",
        "transactions",
        ["asset_id", "transaction_type"],
    )
    op.create_index(
        "ix_audit_logs_resource_type_resource_id",
        "audit_logs",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_resource_type_resource_id", table_name="audit_logs")
    op.drop_index("ix_transactions_asset_id_transaction_type", table_name="transactions")
