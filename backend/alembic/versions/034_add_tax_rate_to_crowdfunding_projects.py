"""Add tax_rate column to crowdfunding_projects."""

from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "034_tax_rate"
down_revision = "033_repayment_breakdown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crowdfunding_projects",
        sa.Column(
            "tax_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="30.00",
        ),
    )


def downgrade() -> None:
    op.drop_column("crowdfunding_projects", "tax_rate")
