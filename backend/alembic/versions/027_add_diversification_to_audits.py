"""Add diversification analysis columns to project_audits.

Revision ID: 027_diversification_audits
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "027_diversification_audits"
down_revision = "026_project_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_audits",
        sa.Column("diversification_impact", sa.String(20), nullable=True),
    )
    op.add_column(
        "project_audits",
        sa.Column("correlation_score", sa.Numeric(precision=4, scale=2), nullable=True),
    )
    op.add_column(
        "project_audits",
        sa.Column("portfolio_concentration", JSONB, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("project_audits", "portfolio_concentration")
    op.drop_column("project_audits", "correlation_score")
    op.drop_column("project_audits", "diversification_impact")
