"""Add goal_type column to goals table.

Revision ID: 023_add_goal_type
"""

from alembic import op
import sqlalchemy as sa


revision = "023_add_goal_type"
down_revision = "022_goal_projection_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if column already exists
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'goals' AND column_name = 'goal_type'"
    ))
    if result.fetchone():
        return

    goal_type = sa.Enum("ASSET", "SAVINGS", name="goaltype")
    goal_type.create(conn, checkfirst=True)

    op.add_column(
        "goals",
        sa.Column("goal_type", goal_type, server_default="ASSET", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("goals", "goal_type")
    sa.Enum(name="goaltype").drop(op.get_bind(), checkfirst=True)
