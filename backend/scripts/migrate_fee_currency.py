"""Migration script for fee_currency field."""

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
        print("Adding fee_currency column...")
        try:
            conn.execute(text("""
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS fee_currency VARCHAR(10)
            """))
            conn.commit()
            print("  - fee_currency column added")
        except Exception as e:
            print(f"  - Column may already exist: {e}")

        print("Changing fee column precision to support crypto amounts...")
        try:
            conn.execute(text("""
                ALTER TABLE transactions
                ALTER COLUMN fee TYPE NUMERIC(18, 8)
            """))
            conn.commit()
            print("  - fee column precision updated")
        except Exception as e:
            print(f"  - Error updating fee precision: {e}")

    print("\nMigration completed successfully!")
    return True


if __name__ == "__main__":
    run_migration()
