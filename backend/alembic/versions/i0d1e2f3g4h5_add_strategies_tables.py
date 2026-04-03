"""add_strategies_tables

Revision ID: i0d1e2f3g4h5
Revises: h9c3d4e5f6g7
Create Date: 2026-04-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "i0d1e2f3g4h5"
down_revision: Union[str, None] = "h9c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums via raw SQL (idempotent)
    op.execute("DO $$ BEGIN CREATE TYPE strategysource AS ENUM ('AI', 'USER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE strategystatus AS ENUM ('PROPOSED', 'ACTIVE', 'PAUSED', 'COMPLETED', 'REJECTED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE actionstatus AS ENUM ('PENDING', 'EXECUTED', 'SKIPPED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # Create tables via raw SQL to avoid SQLAlchemy re-creating enums
    op.execute("""
        CREATE TABLE strategies (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            source strategysource NOT NULL DEFAULT 'USER',
            status strategystatus NOT NULL DEFAULT 'ACTIVE',
            params JSON NOT NULL DEFAULT '{}',
            ai_reasoning TEXT,
            market_regime VARCHAR(50),
            confidence NUMERIC(5, 4),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.create_index("ix_strategies_user_id", "strategies", ["user_id"])

    op.execute("""
        CREATE TABLE strategy_actions (
            id UUID PRIMARY KEY,
            strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            action VARCHAR(50) NOT NULL,
            symbol VARCHAR(50),
            amount NUMERIC(18, 8),
            currency VARCHAR(10) NOT NULL DEFAULT 'EUR',
            reason TEXT,
            status actionstatus NOT NULL DEFAULT 'PENDING',
            scheduled_at TIMESTAMPTZ,
            executed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.create_index("ix_strategy_actions_strategy_id", "strategy_actions", ["strategy_id"])


def downgrade() -> None:
    op.drop_table("strategy_actions")
    op.drop_table("strategies")

    sa.Enum(name="actionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="strategystatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="strategysource").drop(op.get_bind(), checkfirst=True)
