"""Add prediction tracking columns for CI coverage and direction accuracy.

Revision ID: 011
Revises: 010
Create Date: 2026-02-21

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_logs", sa.Column("confidence_low", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("confidence_high", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("accuracy_checked", sa.DateTime(), nullable=True))
    op.add_column("prediction_logs", sa.Column("mape", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("direction_correct", sa.Boolean(), nullable=True))
    op.add_column("prediction_logs", sa.Column("ci_covered", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("prediction_logs", "ci_covered")
    op.drop_column("prediction_logs", "direction_correct")
    op.drop_column("prediction_logs", "mape")
    op.drop_column("prediction_logs", "accuracy_checked")
    op.drop_column("prediction_logs", "confidence_high")
    op.drop_column("prediction_logs", "confidence_low")
