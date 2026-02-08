"""Add simulations table.

Revision ID: 001
Revises:
Create Date: 2024-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create simulations table
    op.create_table(
        'simulations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('simulation_type', sa.Enum('fire', 'projection', 'what_if', 'rebalance', 'dca', name='simulationtype'), nullable=False),
        sa.Column('parameters', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('results', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_simulations_user_id'), 'simulations', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_simulations_user_id'), table_name='simulations')
    op.drop_table('simulations')
    op.execute('DROP TYPE IF EXISTS simulationtype')
