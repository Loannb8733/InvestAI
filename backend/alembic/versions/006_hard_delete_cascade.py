"""Remove soft delete, add CASCADE on foreign keys.

Revision ID: 006_hard_delete_cascade
Revises: 0405cc599456
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_hard_delete_cascade'
down_revision: Union[str, None] = '0405cc599456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Hard-delete all soft-deleted rows (order matters for FK constraints)
    op.execute("DELETE FROM transactions WHERE deleted_at IS NOT NULL")
    op.execute("DELETE FROM assets WHERE deleted_at IS NOT NULL")
    op.execute("DELETE FROM portfolios WHERE deleted_at IS NOT NULL")
    op.execute("DELETE FROM notes WHERE deleted_at IS NOT NULL")
    op.execute("DELETE FROM goals WHERE deleted_at IS NOT NULL")
    op.execute("DELETE FROM users WHERE deleted_at IS NOT NULL")

    # 2. Drop indexes that reference deleted_at
    op.drop_index('ix_transactions_deleted_at', table_name='transactions', if_exists=True)
    op.drop_index('ix_assets_portfolio_id_deleted_at', table_name='assets', if_exists=True)
    op.drop_index('ix_portfolios_user_id_deleted_at', table_name='portfolios', if_exists=True)

    # 3. Drop deleted_at columns
    for table in ['transactions', 'assets', 'portfolios', 'notes', 'goals', 'users']:
        op.drop_column(table, 'deleted_at')

    # 4. Recreate foreign keys with CASCADE / SET NULL
    # --- portfolios.user_id -> CASCADE
    op.drop_constraint('portfolios_user_id_fkey', 'portfolios', type_='foreignkey')
    op.create_foreign_key('portfolios_user_id_fkey', 'portfolios', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- assets.portfolio_id -> CASCADE
    op.drop_constraint('assets_portfolio_id_fkey', 'assets', type_='foreignkey')
    op.create_foreign_key('assets_portfolio_id_fkey', 'assets', 'portfolios', ['portfolio_id'], ['id'], ondelete='CASCADE')

    # --- transactions.asset_id -> CASCADE
    op.drop_constraint('transactions_asset_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key('transactions_asset_id_fkey', 'transactions', 'assets', ['asset_id'], ['id'], ondelete='CASCADE')

    # --- transactions.related_transaction_id -> SET NULL
    op.drop_constraint('transactions_related_transaction_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key('transactions_related_transaction_id_fkey', 'transactions', 'transactions', ['related_transaction_id'], ['id'], ondelete='SET NULL')

    # --- notes.user_id -> CASCADE
    op.drop_constraint('notes_user_id_fkey', 'notes', type_='foreignkey')
    op.create_foreign_key('notes_user_id_fkey', 'notes', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- notes.asset_id -> SET NULL
    op.drop_constraint('notes_asset_id_fkey', 'notes', type_='foreignkey')
    op.create_foreign_key('notes_asset_id_fkey', 'notes', 'assets', ['asset_id'], ['id'], ondelete='SET NULL')

    # --- goals.user_id -> CASCADE
    op.drop_constraint('goals_user_id_fkey', 'goals', type_='foreignkey')
    op.create_foreign_key('goals_user_id_fkey', 'goals', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- alerts.user_id -> CASCADE
    op.drop_constraint('alerts_user_id_fkey', 'alerts', type_='foreignkey')
    op.create_foreign_key('alerts_user_id_fkey', 'alerts', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- alerts.asset_id -> SET NULL
    op.drop_constraint('alerts_asset_id_fkey', 'alerts', type_='foreignkey')
    op.create_foreign_key('alerts_asset_id_fkey', 'alerts', 'assets', ['asset_id'], ['id'], ondelete='SET NULL')

    # --- api_keys.user_id -> CASCADE
    op.drop_constraint('api_keys_user_id_fkey', 'api_keys', type_='foreignkey')
    op.create_foreign_key('api_keys_user_id_fkey', 'api_keys', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- calendar_events.user_id -> CASCADE
    op.drop_constraint('calendar_events_user_id_fkey', 'calendar_events', type_='foreignkey')
    op.create_foreign_key('calendar_events_user_id_fkey', 'calendar_events', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- simulations.user_id -> CASCADE
    op.drop_constraint('simulations_user_id_fkey', 'simulations', type_='foreignkey')
    op.create_foreign_key('simulations_user_id_fkey', 'simulations', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- portfolio_snapshots.user_id -> CASCADE
    op.drop_constraint('portfolio_snapshots_user_id_fkey', 'portfolio_snapshots', type_='foreignkey')
    op.create_foreign_key('portfolio_snapshots_user_id_fkey', 'portfolio_snapshots', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # --- portfolio_snapshots.portfolio_id -> CASCADE
    op.drop_constraint('portfolio_snapshots_portfolio_id_fkey', 'portfolio_snapshots', type_='foreignkey')
    op.create_foreign_key('portfolio_snapshots_portfolio_id_fkey', 'portfolio_snapshots', 'portfolios', ['portfolio_id'], ['id'], ondelete='CASCADE')

    # --- notifications.user_id -> CASCADE
    op.drop_constraint('notifications_user_id_fkey', 'notifications', type_='foreignkey')
    op.create_foreign_key('notifications_user_id_fkey', 'notifications', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # 5. Add new index for portfolios without deleted_at
    op.create_index('ix_portfolios_user_id', 'portfolios', ['user_id'], unique=False)
    op.create_index('ix_assets_portfolio_id', 'assets', ['portfolio_id'], unique=False)


def downgrade() -> None:
    # Re-add deleted_at columns
    for table in ['transactions', 'assets', 'portfolios', 'notes', 'goals', 'users']:
        op.add_column(table, sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Restore indexes
    op.create_index('ix_transactions_deleted_at', 'transactions', ['deleted_at'], unique=False)
    op.create_index('ix_assets_portfolio_id_deleted_at', 'assets', ['portfolio_id', 'deleted_at'], unique=False)
    op.create_index('ix_portfolios_user_id_deleted_at', 'portfolios', ['user_id', 'deleted_at'], unique=False)

    # Drop new indexes
    op.drop_index('ix_portfolios_user_id', table_name='portfolios')
    op.drop_index('ix_assets_portfolio_id', table_name='assets')

    # Recreate FKs without CASCADE (default RESTRICT)
    for fk_name, src_table, ref_table, src_col, ref_col in [
        ('portfolios_user_id_fkey', 'portfolios', 'users', 'user_id', 'id'),
        ('assets_portfolio_id_fkey', 'assets', 'portfolios', 'portfolio_id', 'id'),
        ('transactions_asset_id_fkey', 'transactions', 'assets', 'asset_id', 'id'),
        ('transactions_related_transaction_id_fkey', 'transactions', 'transactions', 'related_transaction_id', 'id'),
        ('notes_user_id_fkey', 'notes', 'users', 'user_id', 'id'),
        ('notes_asset_id_fkey', 'notes', 'assets', 'asset_id', 'id'),
        ('goals_user_id_fkey', 'goals', 'users', 'user_id', 'id'),
        ('alerts_user_id_fkey', 'alerts', 'users', 'user_id', 'id'),
        ('alerts_asset_id_fkey', 'alerts', 'assets', 'asset_id', 'id'),
        ('api_keys_user_id_fkey', 'api_keys', 'users', 'user_id', 'id'),
        ('calendar_events_user_id_fkey', 'calendar_events', 'users', 'user_id', 'id'),
        ('simulations_user_id_fkey', 'simulations', 'users', 'user_id', 'id'),
        ('portfolio_snapshots_user_id_fkey', 'portfolio_snapshots', 'users', 'user_id', 'id'),
        ('portfolio_snapshots_portfolio_id_fkey', 'portfolio_snapshots', 'portfolios', 'portfolio_id', 'id'),
        ('notifications_user_id_fkey', 'notifications', 'users', 'user_id', 'id'),
    ]:
        op.drop_constraint(fk_name, src_table, type_='foreignkey')
        op.create_foreign_key(fk_name, src_table, ref_table, [src_col], [ref_col])
