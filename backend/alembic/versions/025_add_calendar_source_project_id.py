"""Add source_project_id to calendar_events for crowdfunding sync.

Revision ID: 025_calendar_source_project
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "025_calendar_source_project"
down_revision = "024_crowdfunding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column(
            "source_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("crowdfunding_projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_calendar_events_source_project_id",
        "calendar_events",
        ["source_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_source_project_id", table_name="calendar_events")
    op.drop_column("calendar_events", "source_project_id")
