"""Add delay_months column to crowdfunding_projects."""

from alembic import op
import sqlalchemy as sa

revision = "035_delay_months"
down_revision = "034_tax_rate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crowdfunding_projects",
        sa.Column(
            "delay_months",
            sa.Numeric(precision=4, scale=0),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("crowdfunding_projects", "delay_months")
