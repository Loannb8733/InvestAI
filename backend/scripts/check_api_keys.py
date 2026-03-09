"""Check available API keys for re-sync."""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.api_key import APIKey


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(APIKey))
        for key in result.scalars().all():
            print(f"{key.exchange:12s} | status={key.status} | active={key.is_active} | last_sync={key.last_sync_at}")


if __name__ == "__main__":
    asyncio.run(main())
