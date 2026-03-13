#!/usr/bin/env python3
"""Stamp Alembic version table to HEAD on a fresh database.

Run once after deploying to a new database (e.g. Supabase) where tables
were created by SQLAlchemy metadata.create_all() instead of Alembic.

Usage:
    cd backend && python ../scripts/alembic_stamp_head.py

Requires DATABASE_URL env var to be set.
"""

import subprocess
import sys


def main():
    print("Stamping Alembic version to HEAD...")
    result = subprocess.run(
        ["python", "-m", "alembic", "stamp", "head"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print("Verifying current revision...")
    result = subprocess.run(
        ["python", "-m", "alembic", "current"],
        capture_output=True,
        text=True,
    )
    print(result.stdout or "(no output)")
    print("Done. Alembic is now synced with the database schema.")


if __name__ == "__main__":
    main()
