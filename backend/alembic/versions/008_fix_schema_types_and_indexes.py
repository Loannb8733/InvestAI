"""Fix schema types and add missing indexes.

- Change alert.triggered_at from String to DateTime
- Change user.email_verification_expires from String to DateTime
- Change user.password_reset_expires from String to DateTime
- Add index on transactions.executed_at
- Add index on transactions.external_id

Revision ID: 008
Revises: 5e79ca77dcc3
Create Date: 2026-02-20

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "5e79ca77dcc3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix alert.triggered_at: String -> DateTime
    op.execute(
        "ALTER TABLE alerts "
        "ALTER COLUMN triggered_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING CASE WHEN triggered_at IS NOT NULL THEN triggered_at::timestamp with time zone ELSE NULL END"
    )

    # Fix user.email_verification_expires: String -> DateTime
    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN email_verification_expires TYPE TIMESTAMP WITH TIME ZONE "
        "USING CASE WHEN email_verification_expires IS NOT NULL THEN email_verification_expires::timestamp with time zone ELSE NULL END"
    )

    # Fix user.password_reset_expires: String -> DateTime
    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN password_reset_expires TYPE TIMESTAMP WITH TIME ZONE "
        "USING CASE WHEN password_reset_expires IS NOT NULL THEN password_reset_expires::timestamp with time zone ELSE NULL END"
    )

    # Add missing indexes for performance
    op.create_index(
        op.f("ix_transactions_executed_at"),
        "transactions",
        ["executed_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transactions_external_id"),
        "transactions",
        ["external_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_external_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_executed_at"), table_name="transactions")

    op.execute(
        "ALTER TABLE users ALTER COLUMN password_reset_expires TYPE VARCHAR(255) "
        "USING CASE WHEN password_reset_expires IS NOT NULL THEN password_reset_expires::text ELSE NULL END"
    )
    op.execute(
        "ALTER TABLE users ALTER COLUMN email_verification_expires TYPE VARCHAR(255) "
        "USING CASE WHEN email_verification_expires IS NOT NULL THEN email_verification_expires::text ELSE NULL END"
    )
    op.execute(
        "ALTER TABLE alerts ALTER COLUMN triggered_at TYPE VARCHAR(255) "
        "USING CASE WHEN triggered_at IS NOT NULL THEN triggered_at::text ELSE NULL END"
    )
