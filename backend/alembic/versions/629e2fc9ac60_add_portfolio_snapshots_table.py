"""add portfolio snapshots table

Revision ID: 629e2fc9ac60
Revises: 002
Create Date: 2026-01-23 14:13:58.606594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '629e2fc9ac60'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('portfolio_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('portfolio_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('snapshot_date', sa.DateTime(), nullable=False),
        sa.Column('total_value', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('total_invested', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('total_gain_loss', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='EUR'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_portfolio_snapshots_snapshot_date', 'portfolio_snapshots', ['snapshot_date'], unique=False)
    op.create_index('ix_portfolio_snapshots_user_id', 'portfolio_snapshots', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_portfolio_snapshots_user_id', table_name='portfolio_snapshots')
    op.drop_index('ix_portfolio_snapshots_snapshot_date', table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
