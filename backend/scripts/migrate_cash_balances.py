"""Migration script for cash_balances field."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings


def run_migration():
    database_url = settings.DATABASE_URL_SYNC
    print("Connecting to database...")

    engine = create_engine(database_url)

    with engine.connect() as conn:
        print("Adding cash_balances column to portfolios...")
        try:
            conn.execute(text("""
                ALTER TABLE portfolios
                ADD COLUMN IF NOT EXISTS cash_balances JSONB NOT NULL DEFAULT '{}'
            """))
            conn.commit()
            print("  - cash_balances column added")
        except Exception as e:
            print(f"  - Error: {e}")

    print("\nMigration completed successfully!")
    return True


if __name__ == "__main__":
    run_migration()
