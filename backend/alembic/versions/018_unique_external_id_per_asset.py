"""Add partial unique index on (asset_id, external_id) to prevent duplicate imports.

Revision ID: 018_unique_external_id_per_asset
Revises: 017_breakeven_volatility_alerts
Create Date: 2026-03-04

"""
import logging
from typing import Sequence, Union

from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "018_unique_external_id_per_asset"
down_revision: Union[str, None] = "017_breakeven_volatility_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tx_asset_external_id "
            "ON transactions (asset_id, external_id) "
            "WHERE external_id IS NOT NULL AND external_id <> ''"
        )
    except Exception as e:
        logger.warning(
            "Could not create unique index uq_tx_asset_external_id "
            "(possibly duplicates exist): %s",
            e,
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tx_asset_external_id")
