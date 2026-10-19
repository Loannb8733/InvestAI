"""converge transaction amount columns to the model

Revision ID: c4e8f1a2b3d5
Revises: b3d1e07a5c92
Create Date: 2026-10-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e8f1a2b3d5"
down_revision: str | None = "b3d1e07a5c92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TARGET_PRECISION = {"quantity": (30, 12), "price": (24, 12), "fee": (24, 12)}


def _current_precision(column: str) -> tuple[int, int] | None:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = :column"
            ),
            {"column": column},
        )
        .first()
    )
    return (row[0], row[1]) if row and row[0] is not None else None


def upgrade() -> None:
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee_currency VARCHAR(10)")
    for column, (precision, scale) in TARGET_PRECISION.items():
        current = _current_precision(column)
        if current is None:
            continue
        new_scale = max(scale, current[1])
        new_precision = max(precision - scale, current[0] - current[1]) + new_scale
        if (new_precision, new_scale) == current:
            continue
        op.execute(f"ALTER TABLE transactions ALTER COLUMN {column} TYPE NUMERIC({new_precision}, {new_scale})")


def downgrade() -> None:
    raise NotImplementedError("narrowing transaction amount columns would lose data")
