"""Add performance indexes and soft delete to transactions.

Revision ID: 003_add_performance_indexes
Revises: 629e2fc9ac60
Create Date: 2026-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_performance_indexes'
down_revision: Union[str, None] = '629e2fc9ac60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_at column to transactions for soft delete
    op.add_column(
        'transactions',
        sa.Column('deleted_at', sa.DateTime(), nullable=True)
    )

    # Critical indexes for transactions table
    op.create_index(
        'ix_transactions_asset_id_executed_at',
        'transactions',
        ['asset_id', 'executed_at'],
        unique=False
    )
    op.create_index(
        'ix_transactions_executed_at',
        'transactions',
        ['executed_at'],
        unique=False
    )
    op.create_index(
        'ix_transactions_deleted_at',
        'transactions',
        ['deleted_at'],
        unique=False
    )

    # Critical indexes for portfolio_snapshots table
    op.create_index(
        'ix_portfolio_snapshots_user_id_snapshot_date',
        'portfolio_snapshots',
        ['user_id', 'snapshot_date'],
        unique=False
    )
    op.create_index(
        'ix_portfolio_snapshots_portfolio_id_snapshot_date',
        'portfolio_snapshots',
        ['portfolio_id', 'snapshot_date'],
        unique=False
    )

    # Critical indexes for assets table
    op.create_index(
        'ix_assets_portfolio_id_deleted_at',
        'assets',
        ['portfolio_id', 'deleted_at'],
        unique=False
    )
    op.create_index(
        'ix_assets_portfolio_id_symbol',
        'assets',
        ['portfolio_id', 'symbol'],
        unique=False
    )

    # Critical indexes for portfolios table
    op.create_index(
        'ix_portfolios_user_id_deleted_at',
        'portfolios',
        ['user_id', 'deleted_at'],
        unique=False
    )

    # Critical indexes for alerts table
    op.create_index(
        'ix_alerts_user_id_is_active',
        'alerts',
        ['user_id', 'is_active'],
        unique=False
    )
    op.create_index(
        'ix_alerts_asset_id',
        'alerts',
        ['asset_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_alerts_asset_id', table_name='alerts')
    op.drop_index('ix_alerts_user_id_is_active', table_name='alerts')
    op.drop_index('ix_portfolios_user_id_deleted_at', table_name='portfolios')
    op.drop_index('ix_assets_portfolio_id_symbol', table_name='assets')
    op.drop_index('ix_assets_portfolio_id_deleted_at', table_name='assets')
    op.drop_index('ix_portfolio_snapshots_portfolio_id_snapshot_date', table_name='portfolio_snapshots')
    op.drop_index('ix_portfolio_snapshots_user_id_snapshot_date', table_name='portfolio_snapshots')
    op.drop_index('ix_transactions_deleted_at', table_name='transactions')
    op.drop_index('ix_transactions_executed_at', table_name='transactions')
    op.drop_index('ix_transactions_asset_id_executed_at', table_name='transactions')

    # Remove deleted_at column from transactions
    op.drop_column('transactions', 'deleted_at')
