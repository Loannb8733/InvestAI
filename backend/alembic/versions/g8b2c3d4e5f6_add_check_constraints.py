"""add_check_constraints

Add CHECK constraints on financial columns to enforce data integrity
at the database level: quantity >= 0, price >= 0, fee >= 0.

Revision ID: g8b2c3d4e5f6
Revises: f7a1b2c3d4e5
Create Date: 2026-03-21 22:10:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g8b2c3d4e5f6"
down_revision: Union[str, None] = "f7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Transactions: quantity, price, and fee must be non-negative
    op.create_check_constraint(
        "ck_transactions_quantity_positive",
        "transactions",
        "quantity >= 0",
    )
    op.create_check_constraint(
        "ck_transactions_price_positive",
        "transactions",
        "price >= 0",
    )
    op.create_check_constraint(
        "ck_transactions_fee_positive",
        "transactions",
        "fee >= 0",
    )

    # Assets: quantity and avg_buy_price must be non-negative
    op.create_check_constraint(
        "ck_assets_quantity_positive",
        "assets",
        "quantity >= 0",
    )
    op.create_check_constraint(
        "ck_assets_avg_buy_price_positive",
        "assets",
        "avg_buy_price >= 0",
    )

    # Planned orders: amount must be non-negative
    op.create_check_constraint(
        "ck_planned_orders_amount_positive",
        "planned_orders",
        "order_eur >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_planned_orders_amount_positive", "planned_orders", type_="check")
    op.drop_constraint("ck_assets_avg_buy_price_positive", "assets", type_="check")
    op.drop_constraint("ck_assets_quantity_positive", "assets", type_="check")
    op.drop_constraint("ck_transactions_fee_positive", "transactions", type_="check")
    op.drop_constraint("ck_transactions_price_positive", "transactions", type_="check")
    op.drop_constraint("ck_transactions_quantity_positive", "transactions", type_="check")
