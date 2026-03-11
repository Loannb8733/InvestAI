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

    # Use raw SQL to create the table to avoid SQLAlchemy enum before_create events
    op.execute("""
        CREATE TABLE IF NOT EXISTS crowdfunding_projects (
            id UUID PRIMARY KEY,
            asset_id UUID NOT NULL UNIQUE REFERENCES assets(id) ON DELETE CASCADE,
            platform VARCHAR(100) NOT NULL,
            project_name VARCHAR(300),
            description TEXT,
            project_url VARCHAR(500),
            invested_amount NUMERIC(12, 2) NOT NULL,
            annual_rate NUMERIC(6, 3) NOT NULL,
            duration_months NUMERIC(4, 0) NOT NULL,
            repayment_type repaymenttype NOT NULL DEFAULT 'in_fine',
            start_date DATE,
            estimated_end_date DATE,
            actual_end_date DATE,
            status projectstatus NOT NULL DEFAULT 'active',
            total_received NUMERIC(12, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crowdfunding_projects_asset_id ON crowdfunding_projects(asset_id)")


def downgrade() -> None:
    op.drop_table("crowdfunding_projects")
    op.execute("DROP TYPE IF EXISTS projectstatus")
    op.execute("DROP TYPE IF EXISTS repaymenttype")
    # Cannot remove enum value from assettype in PostgreSQL
