"""planned_order_float_to_numeric

Change PlannedOrder.order_eur from Float (IEEE 754) to Numeric(12, 2)
to eliminate floating-point rounding errors on financial amounts.

Revision ID: f7a1b2c3d4e5
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f7a1b2c3d4e5"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # USING casts existing float values to numeric, rounding to 2 decimal places.
    # No data loss: Float values like 150.0 become 150.00.
    op.alter_column(
        "planned_orders",
        "order_eur",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
        existing_server_default=sa.text("0.0"),
        postgresql_using="order_eur::numeric(12,2)",
    )


def downgrade() -> None:
    # Revert to Float. Precision loss possible on values with >15 significant digits.
    op.alter_column(
        "planned_orders",
        "order_eur",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="order_eur::double precision",
    )
