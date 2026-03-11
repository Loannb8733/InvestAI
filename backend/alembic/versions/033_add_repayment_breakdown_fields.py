"""Add interest_amount, capital_amount, tax_amount to crowdfunding_repayments.

Revision ID: 033_repayment_breakdown
Revises: 032_payment_schedules
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa

revision = "033_repayment_breakdown"
down_revision = "032_payment_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crowdfunding_repayments",
        sa.Column("interest_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "crowdfunding_repayments",
        sa.Column("capital_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "crowdfunding_repayments",
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crowdfunding_repayments", "tax_amount")
    op.drop_column("crowdfunding_repayments", "capital_amount")
    op.drop_column("crowdfunding_repayments", "interest_amount")
