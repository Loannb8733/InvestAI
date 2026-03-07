"""Add project_audits table for AI-powered crowdfunding analysis.

Revision ID: 026_project_audits
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


revision = "026_project_audits"
down_revision = "025_calendar_source_project"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_audits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crowdfunding_projects.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # Input
        sa.Column("file_names", ARRAY(sa.Text), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=True),
        # Extracted data
        sa.Column("project_name", sa.String(300), nullable=True),
        sa.Column("operator", sa.String(200), nullable=True),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("tri", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("duration_min", sa.Integer, nullable=True),
        sa.Column("duration_max", sa.Integer, nullable=True),
        sa.Column("collection_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("margin_percent", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("ltv", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("ltc", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("pre_sales_percent", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("equity_contribution", sa.Numeric(precision=14, scale=2), nullable=True),
        # Guarantees & admin
        sa.Column("guarantees", JSONB, server_default="[]"),
        sa.Column("admin_status", sa.String(100), nullable=True),
        # Scoring
        sa.Column("score_operator", sa.Integer, nullable=True),
        sa.Column("score_location", sa.Integer, nullable=True),
        sa.Column("score_guarantees", sa.Integer, nullable=True),
        sa.Column("score_risk_return", sa.Integer, nullable=True),
        sa.Column("score_admin", sa.Integer, nullable=True),
        sa.Column("risk_score", sa.Integer, nullable=True),
        # Analysis
        sa.Column("points_forts", JSONB, server_default="[]"),
        sa.Column("points_vigilance", JSONB, server_default="[]"),
        sa.Column("red_flags", JSONB, server_default="[]"),
        sa.Column("verdict", sa.String(20), nullable=True),
        sa.Column("suggested_investment", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("raw_analysis", sa.Text, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("project_audits")
