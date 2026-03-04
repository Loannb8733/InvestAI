"""add_crowdfunding_fields_to_assets

Revision ID: 293ca70d7b68
Revises: 8b0d743ab1c3
Create Date: 2026-03-01 22:58:35.807127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '293ca70d7b68'
down_revision: Union[str, None] = '8b0d743ab1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assets', sa.Column('interest_rate', sa.Numeric(precision=6, scale=3), nullable=True))
    op.add_column('assets', sa.Column('maturity_date', sa.Date(), nullable=True))
    op.add_column('assets', sa.Column('project_status', sa.String(length=20), nullable=True))
    op.add_column('assets', sa.Column('invested_amount', sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('assets', 'invested_amount')
    op.drop_column('assets', 'project_status')
    op.drop_column('assets', 'maturity_date')
    op.drop_column('assets', 'interest_rate')
