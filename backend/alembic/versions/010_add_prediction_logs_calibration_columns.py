"""Add calibration columns to prediction_logs table.

Revision ID: 010
Revises: 009
Create Date: 2026-02-21

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_logs", sa.Column("predicted_price", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("target_date", sa.DateTime(), nullable=True))
    op.add_column("prediction_logs", sa.Column("horizon_days", sa.Integer(), nullable=True))
    op.add_column("prediction_logs", sa.Column("actual_price", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("error_pct", sa.Float(), nullable=True))
    op.add_column("prediction_logs", sa.Column("models_detail", sa.JSON(), nullable=True))
    op.create_index("ix_prediction_logs_target_date", "prediction_logs", ["target_date"])


def downgrade() -> None:
    op.drop_index("ix_prediction_logs_target_date", table_name="prediction_logs")
    op.drop_column("prediction_logs", "models_detail")
    op.drop_column("prediction_logs", "error_pct")
    op.drop_column("prediction_logs", "actual_price")
    op.drop_column("prediction_logs", "horizon_days")
    op.drop_column("prediction_logs", "target_date")
    op.drop_column("prediction_logs", "predicted_price")
