"""add fx_daily_rates

Persists ECB daily reference rates (FIN-01) so the exchange sync and the historical
backfill can resolve a trade's FX rate at its execution date without per-trade network
calls. The cost-basis engine reads Transaction.conversion_rate, which sync/backfill fill
from this table.

Revision ID: m4h5i6j7k8l9
Revises: l3g4h5i6j7k8
Create Date: 2026-06-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "m4h5i6j7k8l9"
down_revision: Union[str, Sequence[str]] = "l3g4h5i6j7k8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: table may already exist if DB was created via create_all().
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT to_regclass('public.fx_daily_rates')"
        )
    ).scalar()
    if exists is not None:
        return

    op.create_table(
        "fx_daily_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(length=10), nullable=False),
        sa.Column("quote_currency", sa.String(length=10), nullable=False),
        sa.Column("rate", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="ecb"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "rate_date", "base_currency", "quote_currency", name="uq_fx_daily_rates_date_pair"
        ),
    )
    op.create_index("ix_fx_daily_rates_rate_date", "fx_daily_rates", ["rate_date"])
    op.create_index(
        "ix_fx_daily_rates_pair_date",
        "fx_daily_rates",
        ["base_currency", "quote_currency", "rate_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_fx_daily_rates_pair_date", table_name="fx_daily_rates")
    op.drop_index("ix_fx_daily_rates_rate_date", table_name="fx_daily_rates")
    op.drop_table("fx_daily_rates")
