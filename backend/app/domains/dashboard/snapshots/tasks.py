import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.dashboard.snapshots import repository
from app.domains.dashboard.snapshots.service import snapshot_service
from app.domains.portfolio.models import Portfolio
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _snapshot_portfolio(
    db: AsyncSession, user_id: str, portfolio: Portfolio, start: datetime, end: datetime
) -> None:
    if await repository.has_portfolio_snapshot(db, user_id, portfolio.id, start, end):
        return
    metrics = await metrics_service.get_portfolio_performance(db, str(portfolio.id), "EUR")
    if metrics.get("total_value", 0) <= 0:
        return
    db.add(
        PortfolioSnapshot(
            user_id=user_id,
            portfolio_id=portfolio.id,
            snapshot_date=datetime.now(UTC),
            total_value=Decimal(str(metrics.get("total_value", 0))),
            total_invested=Decimal(str(metrics.get("total_invested", 0))),
            total_gain_loss=Decimal(str(metrics.get("total_gain_loss", 0))),
            currency="EUR",
        )
    )
    await db.flush()


async def _snapshot_portfolios(db: AsyncSession, user_id: str, start: datetime, end: datetime) -> None:
    portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
    for portfolio in portfolios:
        try:
            async with db.begin_nested():
                await _snapshot_portfolio(db, user_id, portfolio, start, end)
        except IntegrityError:
            logger.debug("Race: portfolio snapshot already created for portfolio=%s", portfolio.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create snapshot for portfolio %s: %s", portfolio.id, exc)


async def _snapshot_user(db: AsyncSession, user_id: str) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    if await repository.has_global_snapshot(db, user_id, start, end):
        logger.debug("Snapshot already exists for user %s today", user_id)
        return 0
    snapshot = await snapshot_service.create_user_snapshot(db, user_id)
    await _snapshot_portfolios(db, user_id, start, end)
    await db.commit()
    return 1 if snapshot else 0


async def create_all_snapshots() -> dict[str, int]:
    """Crée l'instantané du jour de chaque compte et de ses portefeuilles ; un échec n'arrête pas les suivants."""
    async with session_factory() as db:
        user_ids = await repository.users_with_portfolio(db)
        success = failed = 0
        for user_id in user_ids:
            try:
                success += await _snapshot_user(db, user_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to create snapshot for user %s: %s", user_id, exc)
                failed += 1
        return {"total": len(user_ids), "success": success, "failed": failed}


async def delete_old_snapshots(days_to_keep: int = 365) -> dict[str, int]:
    """Supprime les instantanés plus anciens que `days_to_keep` jours."""
    async with session_factory() as db:
        cutoff = datetime.now(UTC) - timedelta(days=days_to_keep)
        count = await repository.count_older_than(db, cutoff)
        if count > 0:
            await repository.delete_older_than(db, cutoff)
            await db.commit()
            logger.info("Deleted %s snapshots older than %s days", count, days_to_keep)
        return {"deleted": count}


@celery_app.task(name="app.domains.dashboard.snapshots.tasks.create_daily_snapshots")  # type: ignore[untyped-decorator]
def create_daily_snapshots() -> dict[str, Any]:
    """Crée les instantanés quotidiens de tous les comptes."""
    result: dict[str, Any] = run_async(create_all_snapshots())
    return result


@celery_app.task(name="app.domains.dashboard.snapshots.tasks.cleanup_old_snapshots")  # type: ignore[untyped-decorator]
def cleanup_old_snapshots(days_to_keep: int = 365) -> dict[str, Any]:
    """Purge les instantanés anciens."""
    result: dict[str, Any] = run_async(delete_old_snapshots(days_to_keep))
    return result
