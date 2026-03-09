"""Add missing performance indexes on asset_type, transaction_type, exchange.

Revision ID: 029_performance_indexes
Revises: 028_project_documents
"""

from alembic import op

revision = "029_performance_indexes"
down_revision = "028_project_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"], if_not_exists=True)
    op.create_index("ix_transactions_transaction_type", "transactions", ["transaction_type"], if_not_exists=True)
    op.create_index("ix_api_keys_exchange", "api_keys", ["exchange"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_api_keys_exchange", table_name="api_keys")
    op.drop_index("ix_transactions_transaction_type", table_name="transactions")
    op.drop_index("ix_assets_asset_type", table_name="assets")
