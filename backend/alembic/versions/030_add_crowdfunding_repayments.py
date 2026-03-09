"""Add crowdfunding_repayments table.

Revision ID: 030_crowdfunding_repayments
Revises: 029_performance_indexes
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "030_crowdfunding_repayments"
down_revision = "029_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum if not exists
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE paymenttype AS ENUM ('interest', 'capital', 'both'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.execute("""
        CREATE TABLE crowdfunding_repayments (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES crowdfunding_projects(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            payment_date DATE NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            payment_type paymenttype NOT NULL,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.create_index("ix_crowdfunding_repayments_project_id", "crowdfunding_repayments", ["project_id"])
    op.create_index("ix_crowdfunding_repayments_user_id", "crowdfunding_repayments", ["user_id"])


def downgrade() -> None:
    op.drop_table("crowdfunding_repayments")
    op.execute("DROP TYPE IF EXISTS paymenttype")
