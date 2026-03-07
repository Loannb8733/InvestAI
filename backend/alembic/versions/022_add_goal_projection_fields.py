"""Add deadline_date, priority, strategy_type to goals table.

Revision ID: 022_goal_projection_fields
"""

from alembic import op
import sqlalchemy as sa


revision = "022_goal_projection_fields"
down_revision = "021_planned_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if columns already exist (SQLAlchemy create_all may have added them)
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'goals' AND column_name = 'deadline_date'"
    ))
    if result.fetchone():
        return  # Columns already exist

    # Create enum types (checkfirst handles existing enums from create_all)
    goal_priority = sa.Enum("LOW", "MEDIUM", "HIGH", name="goalpriority")
    goal_strategy = sa.Enum("AGGRESSIVE", "MODERATE", "CONSERVATIVE", name="goalstrategy")
    goal_priority.create(conn, checkfirst=True)
    goal_strategy.create(conn, checkfirst=True)

    op.add_column("goals", sa.Column("deadline_date", sa.Date(), nullable=True))
    op.add_column(
        "goals",
        sa.Column("priority", goal_priority, server_default="MEDIUM", nullable=False),
    )
    op.add_column(
        "goals",
        sa.Column("strategy_type", goal_strategy, server_default="MODERATE", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("goals", "strategy_type")
    op.drop_column("goals", "priority")
    op.drop_column("goals", "deadline_date")
    sa.Enum(name="goalstrategy").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="goalpriority").drop(op.get_bind(), checkfirst=True)
