import pytest
import redis.asyncio as aioredis
from celery.schedules import crontab, maybe_schedule

from app.core.redis_client import redis_async_url
from app.domains.system.scheduler import STATE_KEY, Entry, Scheduler
from app.tasks.celery_app import celery_app

pytestmark = pytest.mark.usefixtures("empty_test_redis")


async def _ok() -> None:
    return None


async def test_only_tasks_a_restart_could_skip_are_saved_in_redis() -> None:
    rhythms = {
        "five-minutes": maybe_schedule(300.0, app=celery_app),
        "half-hour": maybe_schedule(1800.0, app=celery_app),
        "hourly": maybe_schedule(3600.0, app=celery_app),
        "nightly": maybe_schedule(crontab(hour=0, minute=0), app=celery_app),
    }
    scheduler = Scheduler({name: Entry(name, "app.tasks.demo.job", rhythm, _ok) for name, rhythm in rhythms.items()})
    await scheduler.load()
    for name in rhythms:
        await scheduler.run(name)
    client = aioredis.from_url(redis_async_url(), decode_responses=True)
    saved = sorted(await client.hkeys(STATE_KEY))
    await client.aclose()
    assert saved == ["hourly", "nightly"]
