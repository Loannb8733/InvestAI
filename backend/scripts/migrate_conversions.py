"""Migration script for conversion fields."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

def run_migration():
    database_url = settings.DATABASE_URL_SYNC
    print(f"Connecting to database...")

    engine = create_engine(database_url)

    with engine.connect() as conn:
        print("Adding new transaction types...")
        try:
            # Use UPPERCASE to match existing enum values (BUY, SELL, etc.)
            conn.execute(text("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'CONVERSION_OUT'"))
            conn.execute(text("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'CONVERSION_IN'"))
            conn.commit()
            print("  - Transaction types added")
        except Exception as e:
            print(f"  - Transaction types may already exist: {e}")

        print("Adding new columns...")
        try:
            conn.execute(text("""
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS related_transaction_id UUID REFERENCES transactions(id)
            """))
            conn.commit()
            print("  - related_transaction_id column added")
        except Exception as e:
            print(f"  - Column may already exist: {e}")

        try:
            conn.execute(text("""
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS conversion_rate NUMERIC(18, 12)
            """))
            conn.commit()
            print("  - conversion_rate column added")
        except Exception as e:
            print(f"  - Column may already exist: {e}")

        print("Creating index...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_transactions_related_transaction_id
                ON transactions(related_transaction_id)
            """))
            conn.commit()
            print("  - Index created")
        except Exception as e:
            print(f"  - Index may already exist: {e}")

    print("\nMigration completed successfully!")
    return True

if __name__ == "__main__":
    run_migration()
