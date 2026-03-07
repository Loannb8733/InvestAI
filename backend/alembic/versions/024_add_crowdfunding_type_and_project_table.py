"""Add CROWDFUNDING asset type and crowdfunding_projects table.

Revision ID: 024_crowdfunding
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "024_crowdfunding"
down_revision = "023_add_goal_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL does not allow ALTER TYPE inside a transaction
    op.execute("COMMIT")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'CROWDFUNDING'")
    op.execute("BEGIN")

    # Create enums via raw SQL to avoid SQLAlchemy checkfirst issues
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'repaymenttype') THEN
                CREATE TYPE repaymenttype AS ENUM ('in_fine', 'amortizable');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'projectstatus') THEN
                CREATE TYPE projectstatus AS ENUM ('funding', 'active', 'completed', 'delayed', 'defaulted');
            END IF;
        END $$;
    """)

    op.create_table(
        "crowdfunding_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        # Platform info
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("project_name", sa.String(300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_url", sa.String(500), nullable=True),
        # Financial terms
        sa.Column("invested_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("annual_rate", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("duration_months", sa.Numeric(precision=4, scale=0), nullable=False),
        sa.Column(
            "repayment_type",
            sa.Enum("in_fine", "amortizable", name="repaymenttype", create_type=False),
            nullable=False,
            server_default="in_fine",
        ),
        # Timeline
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("estimated_end_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        # Status
        sa.Column(
            "status",
            sa.Enum(
                "funding", "active", "completed", "delayed", "defaulted",
                name="projectstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        # Tracking
        sa.Column(
            "total_received",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("crowdfunding_projects")
    op.execute("DROP TYPE IF EXISTS projectstatus")
    op.execute("DROP TYPE IF EXISTS repaymenttype")
    # Cannot remove enum value from assettype in PostgreSQL
