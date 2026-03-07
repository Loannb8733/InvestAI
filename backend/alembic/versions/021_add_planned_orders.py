"""Add planned_orders table for Telegram signal-to-action flow.

Revision ID: 021_planned_orders
Revises: 020_user_telegram_fields
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "021_planned_orders"
down_revision: Union[str, None] = "020_user_telegram_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planned_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("order_eur", sa.Float, nullable=False, server_default="0"),
        sa.Column("alpha_score", sa.Float, nullable=True),
        sa.Column("regime", sa.String(20), nullable=True),
        sa.Column("prob_ruin_before", sa.Float, nullable=True),
        sa.Column("prob_ruin_after", sa.Float, nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="telegram"),
        sa.Column(
            "status",
            sa.Enum("pending", "executed", "cancelled", name="plannedorderstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("planned_orders")
    op.execute("DROP TYPE IF EXISTS plannedorderstatus")
