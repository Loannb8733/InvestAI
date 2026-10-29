from typing import Any

from app.core.db.session import session_factory
from app.domains.notifications import reports
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


async def run_weekly_reports() -> dict[str, Any]:
    async with session_factory() as db:
        return await reports.weekly_reports(db)


async def run_monthly_reports() -> dict[str, Any]:
    async with session_factory() as db:
        return await reports.monthly_reports(db)


async def run_daily_digest() -> dict[str, Any]:
    async with session_factory() as db:
        return await reports.daily_digest(db)


@celery_app.task(name="app.domains.notifications.tasks.send_weekly_reports")  # type: ignore[untyped-decorator]
def send_weekly_reports() -> dict[str, Any]:
    """Rapports hebdomadaires de performance."""
    result: dict[str, Any] = run_async(run_weekly_reports())
    return result


@celery_app.task(name="app.domains.notifications.tasks.send_monthly_reports")  # type: ignore[untyped-decorator]
def send_monthly_reports() -> dict[str, Any]:
    """Rapports mensuels de performance."""
    result: dict[str, Any] = run_async(run_monthly_reports())
    return result


@celery_app.task(name="app.domains.notifications.tasks.send_daily_digest")  # type: ignore[untyped-decorator]
def send_daily_digest() -> dict[str, Any]:
    """Résumés quotidiens des alertes."""
    result: dict[str, Any] = run_async(run_daily_digest())
    return result
