"""unique daily portfolio_snapshot per (user, portfolio, date)

Adds two partial UNIQUE indexes on ``portfolio_snapshots`` so the
TOCTOU race in :meth:`SnapshotService.create_user_snapshot_if_missing` and in
the daily-snapshot cron can no longer produce two rows for the same calendar
day (UTC). The code path now catches the IntegrityError that the constraint
raises in the rare race window instead of relying on a check-then-insert.

Two indexes are needed because per-portfolio snapshots carry ``portfolio_id``
while the global user snapshot stores ``portfolio_id IS NULL``, and a single
UNIQUE that includes ``portfolio_id`` would treat NULLs as distinct — which is
exactly the global case we want to constrain.

Pre-deduplication: any existing duplicate rows would make ``CREATE UNIQUE
INDEX`` fail at deploy. Before creating the indexes we delete duplicates,
keeping the most recently created row per (user, portfolio?, day).

Revision ID: n5i6j7k8l9m0
Revises: m4h5i6j7k8l9
Create Date: 2026-06-06

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n5i6j7k8l9m0"
down_revision: Union[str, Sequence[str]] = "m4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Partial UNIQUE on the global user-level snapshot row (portfolio_id IS NULL).
_GLOBAL_INDEX = "uq_portfolio_snapshots_user_day_global"
# Partial UNIQUE on per-portfolio snapshot rows (portfolio_id IS NOT NULL).
_PER_PORTFOLIO_INDEX = "uq_portfolio_snapshots_user_portfolio_day"


def _drop_duplicates(conn: sa.engine.Connection, scope_sql: str, partition_cols: str) -> None:
    """Keep the most recently created row per partition, delete the rest.

    ``scope_sql`` filters the rows we constrain (e.g. ``portfolio_id IS NULL``).
    ``partition_cols`` is the PARTITION BY expression matching the index.
    """
    conn.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY {partition_cols}
                           ORDER BY created_at DESC NULLS LAST, id DESC
                       ) AS rn
                FROM portfolio_snapshots
                WHERE {scope_sql}
            )
            DELETE FROM portfolio_snapshots
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotency: skip if the indexes are already present (defensive against
    # re-runs and against environments where someone created them by hand).
    has_global = conn.execute(sa.text("SELECT to_regclass(:n)"), {"n": f"public.{_GLOBAL_INDEX}"}).scalar()
    has_per_portfolio = conn.execute(
        sa.text("SELECT to_regclass(:n)"), {"n": f"public.{_PER_PORTFOLIO_INDEX}"}
    ).scalar()
    if has_global is not None and has_per_portfolio is not None:
        return

    if has_global is None:
        _drop_duplicates(
            conn,
            scope_sql="portfolio_id IS NULL",
            partition_cols="user_id, ((snapshot_date AT TIME ZONE 'UTC')::date)",
        )
        op.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {_GLOBAL_INDEX}
                ON portfolio_snapshots (
                    user_id,
                    ((snapshot_date AT TIME ZONE 'UTC')::date)
                )
                WHERE portfolio_id IS NULL
                """
            )
        )

    if has_per_portfolio is None:
        _drop_duplicates(
            conn,
            scope_sql="portfolio_id IS NOT NULL",
            partition_cols="user_id, portfolio_id, ((snapshot_date AT TIME ZONE 'UTC')::date)",
        )
        op.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {_PER_PORTFOLIO_INDEX}
                ON portfolio_snapshots (
                    user_id,
                    portfolio_id,
                    ((snapshot_date AT TIME ZONE 'UTC')::date)
                )
                WHERE portfolio_id IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_PER_PORTFOLIO_INDEX}"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_GLOBAL_INDEX}"))
