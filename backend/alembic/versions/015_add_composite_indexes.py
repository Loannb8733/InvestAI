"""Add composite indexes for query performance.

Revision ID: 015_composite_indexes
Revises: 014_price_at_creation
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_composite_indexes"
down_revision: Union[str, None] = "014_price_at_creation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for transactions: asset_id + executed_at (used by reports, tax, analytics)
    op.create_index(
        "ix_transactions_asset_id_executed_at",
        "transactions",
        ["asset_id", "executed_at"],
    )
    # Composite index for prediction_logs: symbol + target_date (used by accuracy checks)
    op.create_index(
        "ix_prediction_logs_symbol_target_date",
        "prediction_logs",
        ["symbol", "target_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_logs_symbol_target_date", table_name="prediction_logs")
    op.drop_index("ix_transactions_asset_id_executed_at", table_name="transactions")
