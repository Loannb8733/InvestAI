"""drop email verification columns

Revision ID: e6a0b5c7d8f9
Revises: d5f9a3b4c6e7
Create Date: 2026-10-20 10:00:00.000000

L'inscription créait déjà les comptes vérifiés et la connexion n'a jamais lu ces
colonnes : la vérification d'email est retirée.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e6a0b5c7d8f9"
down_revision: str | None = "d5f9a3b4c6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("email_verified", "email_verification_token", "email_verification_expires")


def upgrade() -> None:
    for column in COLUMNS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}")


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_expires TIMESTAMP WITH TIME ZONE")
