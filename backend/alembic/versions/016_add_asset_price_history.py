"""Add asset_price_history table for persistent historical prices.

Revision ID: 016_asset_price_history
Revises: 015_composite_indexes
Create Date: 2026-03-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "016_asset_price_history"
down_revision: Union[str, None] = "015_composite_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_price_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("price_date", sa.Date, nullable=False),
        sa.Column("price_eur", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="coingecko"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("symbol", "price_date", name="uq_symbol_price_date"),
    )
    op.create_index("ix_asset_price_history_symbol", "asset_price_history", ["symbol"])
    op.create_index("ix_asset_price_history_symbol_date", "asset_price_history", ["symbol", "price_date"])


def downgrade() -> None:
    op.drop_index("ix_asset_price_history_symbol_date", table_name="asset_price_history")
    op.drop_index("ix_asset_price_history_symbol", table_name="asset_price_history")
    op.drop_table("asset_price_history")
