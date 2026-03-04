"""Add price_at_creation to prediction_logs for direction tracking.

Revision ID: 014_price_at_creation
Revises: 293ca70d7b68
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "014_price_at_creation"
down_revision: Union[str, None] = "293ca70d7b68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prediction_logs",
        sa.Column("price_at_creation", sa.Numeric(18, 8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prediction_logs", "price_at_creation")
