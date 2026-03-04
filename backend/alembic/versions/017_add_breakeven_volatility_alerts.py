"""Add TARGET_BREAK_EVEN and VOLATILITY_SPIKE alert conditions.

Revision ID: 017_breakeven_volatility_alerts
Revises: 016_asset_price_history
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_breakeven_volatility_alerts"
down_revision: Union[str, None] = "016_asset_price_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy stores Enum .name (uppercase) in PostgreSQL
    op.execute("ALTER TYPE alertcondition ADD VALUE IF NOT EXISTS 'TARGET_BREAK_EVEN'")
    op.execute("ALTER TYPE alertcondition ADD VALUE IF NOT EXISTS 'VOLATILITY_SPIKE'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    pass
