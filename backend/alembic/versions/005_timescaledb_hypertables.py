"""Convert portfolio_snapshots to TimescaleDB hypertable.

Revision ID: 005_timescaledb_hypertables
Revises: 004_add_notifications_table
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_timescaledb_hypertables'
down_revision: Union[str, None] = '004_add_notifications_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure TimescaleDB extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # Convert snapshot_date to TIMESTAMPTZ (TimescaleDB best practice)
    op.execute("""
        ALTER TABLE portfolio_snapshots
        ALTER COLUMN snapshot_date TYPE TIMESTAMPTZ
        USING snapshot_date AT TIME ZONE 'UTC'
    """)

    # Drop existing primary key (UUID only) and recreate as composite
    # This is required because TimescaleDB needs the partitioning column
    # in the primary key
    op.execute("""
        ALTER TABLE portfolio_snapshots DROP CONSTRAINT portfolio_snapshots_pkey
    """)
    op.execute("""
        ALTER TABLE portfolio_snapshots
        ADD CONSTRAINT portfolio_snapshots_pkey PRIMARY KEY (id, snapshot_date)
    """)

    # Now convert to hypertable
    op.execute("""
        SELECT create_hypertable(
            'portfolio_snapshots',
            'snapshot_date',
            migrate_data => true,
            if_not_exists => true
        )
    """)

    # Add compression policy (compress chunks older than 30 days)
    op.execute("""
        ALTER TABLE portfolio_snapshots SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'user_id, portfolio_id',
            timescaledb.compress_orderby = 'snapshot_date DESC'
        )
    """)
    op.execute("""
        SELECT add_compression_policy(
            'portfolio_snapshots',
            INTERVAL '30 days',
            if_not_exists => true
        )
    """)

    # Add retention policy (keep 5 years of snapshots)
    op.execute("""
        SELECT add_retention_policy(
            'portfolio_snapshots',
            INTERVAL '5 years',
            if_not_exists => true
        )
    """)

    # Create continuous aggregate for monthly portfolio performance
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS portfolio_snapshots_monthly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 month', snapshot_date) AS month,
            user_id,
            portfolio_id,
            last(total_value, snapshot_date) AS end_value,
            first(total_value, snapshot_date) AS start_value,
            max(total_value) AS max_value,
            min(total_value) AS min_value,
            last(total_invested, snapshot_date) AS total_invested,
            last(total_gain_loss, snapshot_date) AS total_gain_loss,
            count(*) AS snapshot_count
        FROM portfolio_snapshots
        GROUP BY month, user_id, portfolio_id
    """)

    # Refresh policy for the continuous aggregate
    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'portfolio_snapshots_monthly',
            start_offset => INTERVAL '3 months',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day',
            if_not_exists => true
        )
    """)


def downgrade() -> None:
    # Remove continuous aggregate and policies
    op.execute("DROP MATERIALIZED VIEW IF EXISTS portfolio_snapshots_monthly CASCADE")

    op.execute("""
        SELECT remove_compression_policy('portfolio_snapshots', if_exists => true)
    """)
    op.execute("""
        SELECT remove_retention_policy('portfolio_snapshots', if_exists => true)
    """)

    # Note: Cannot easily revert hypertable to regular table
