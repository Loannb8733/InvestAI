"""add_missing_fk_indexes

Postgres does NOT auto-index foreign keys. Several hot FK / time-range columns
were left unindexed, forcing sequential scans on filtered and joined queries:

- portfolio_snapshots(user_id, snapshot_date) — composite for the "Patrimoine
  global" evolution chart (per-user, ordered by date); supersedes the plain
  user_id lookups too.
- portfolio_snapshots(portfolio_id) — per-portfolio snapshot filtering.
- alerts(asset_id) — alerts filtered by asset.
- notes(asset_id) — notes filtered by asset.
- prediction_logs(user_id) — per-user prediction history.
- project_documents(audit_id) — documents by audit.
- crowdfunding_payment_schedules(repayment_id) — schedule rows by repayment.

Revision ID: l3g4h5i6j7k8
Revises: k2f3g4h5i6j7
Create Date: 2026-06-01 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l3g4h5i6j7k8"
down_revision: Union[str, Sequence[str]] = "k2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolio_snapshots_user_id_snapshot_date",
        "portfolio_snapshots",
        ["user_id", "snapshot_date"],
    )
    op.create_index(
        "ix_portfolio_snapshots_portfolio_id",
        "portfolio_snapshots",
        ["portfolio_id"],
    )
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])
    op.create_index("ix_notes_asset_id", "notes", ["asset_id"])
    op.create_index("ix_prediction_logs_user_id", "prediction_logs", ["user_id"])
    op.create_index("ix_project_documents_audit_id", "project_documents", ["audit_id"])
    op.create_index(
        "ix_crowdfunding_payment_schedules_repayment_id",
        "crowdfunding_payment_schedules",
        ["repayment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crowdfunding_payment_schedules_repayment_id",
        table_name="crowdfunding_payment_schedules",
    )
    op.drop_index("ix_project_documents_audit_id", table_name="project_documents")
    op.drop_index("ix_prediction_logs_user_id", table_name="prediction_logs")
    op.drop_index("ix_notes_asset_id", table_name="notes")
    op.drop_index("ix_alerts_asset_id", table_name="alerts")
    op.drop_index("ix_portfolio_snapshots_portfolio_id", table_name="portfolio_snapshots")
    op.drop_index(
        "ix_portfolio_snapshots_user_id_snapshot_date",
        table_name="portfolio_snapshots",
    )
