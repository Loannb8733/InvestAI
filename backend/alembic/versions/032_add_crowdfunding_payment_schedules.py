"""Add crowdfunding_payment_schedules table and interest_frequency column.

Revision ID: 032_payment_schedules
Revises: 031_transaction_internal_hash
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "032_payment_schedules"
down_revision = "031_transaction_internal_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crowdfunding_payment_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column(
            "expected_capital",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "expected_interest",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_completed", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "repayment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crowdfunding_repayments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_cps_project_id",
        "crowdfunding_payment_schedules",
        ["project_id"],
    )
    op.create_index(
        "ix_cps_project_due_date",
        "crowdfunding_payment_schedules",
        ["project_id", "due_date"],
    )

    op.add_column(
        "crowdfunding_projects",
        sa.Column(
            "interest_frequency",
            sa.String(20),
            nullable=True,
            server_default="at_maturity",
        ),
    )


def downgrade() -> None:
    op.drop_column("crowdfunding_projects", "interest_frequency")
    op.drop_index("ix_cps_project_due_date")
    op.drop_index("ix_cps_project_id")
    op.drop_table("crowdfunding_payment_schedules")
