"""Portfolio snapshot tasks for historical value tracking."""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy import select, func, and_

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.asset import Asset
from app.services.snapshot_service import snapshot_service
from app.services.metrics_service import metrics_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_all_snapshots_async() -> dict:
    """Create daily snapshots for all users with portfolios."""
    async with AsyncSessionLocal() as db:
        # Get all users with at least one portfolio
        result = await db.execute(
            select(User.id).where(
                User.id.in_(
                    select(Portfolio.user_id).distinct()
                )
            )
        )
        user_ids = [str(row[0]) for row in result.fetchall()]

        if not user_ids:
            logger.info("No users with portfolios found for snapshots")
            return {"total": 0, "success": 0, "failed": 0}

        logger.info(f"Creating snapshots for {len(user_ids)} users")

        success_count = 0
        failed_count = 0

        for user_id in user_ids:
            try:
                # Check if snapshot already exists for today
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)

                existing = await db.execute(
                    select(func.count(PortfolioSnapshot.id)).where(
                        and_(
                            PortfolioSnapshot.user_id == user_id,
                            PortfolioSnapshot.snapshot_date >= today_start,
                            PortfolioSnapshot.snapshot_date < today_end,
                            PortfolioSnapshot.portfolio_id.is_(None),  # Global snapshot
                        )
                    )
                )
                if existing.scalar() > 0:
                    logger.debug(f"Snapshot already exists for user {user_id} today")
                    continue

                # Create global (user-level) snapshot
                snapshot = await snapshot_service.create_user_snapshot(db, user_id)
                if snapshot:
                    logger.info(
                        f"Created snapshot for user {user_id}: "
                        f"value={snapshot.total_value}, invested={snapshot.total_invested}"
                    )
                    success_count += 1

                # Also create per-portfolio snapshots
                portfolios_result = await db.execute(
                    select(Portfolio).where(Portfolio.user_id == user_id)
                )
                portfolios = portfolios_result.scalars().all()

                for portfolio in portfolios:
                    try:
                        # Check if portfolio snapshot exists for today
                        existing_portfolio = await db.execute(
                            select(func.count(PortfolioSnapshot.id)).where(
                                and_(
                                    PortfolioSnapshot.user_id == user_id,
                                    PortfolioSnapshot.portfolio_id == portfolio.id,
                                    PortfolioSnapshot.snapshot_date >= today_start,
                                    PortfolioSnapshot.snapshot_date < today_end,
                                )
                            )
                        )
                        if existing_portfolio.scalar() > 0:
                            continue

                        # Get portfolio metrics
                        metrics = await metrics_service.get_portfolio_metrics(
                            db, str(portfolio.id), "EUR"
                        )

                        if metrics.get("total_value", 0) > 0:
                            portfolio_snapshot = PortfolioSnapshot(
                                user_id=user_id,
                                portfolio_id=portfolio.id,
                                snapshot_date=datetime.utcnow(),
                                total_value=Decimal(str(metrics.get("total_value", 0))),
                                total_invested=Decimal(str(metrics.get("total_invested", 0))),
                                total_gain_loss=Decimal(str(metrics.get("total_gain_loss", 0))),
                                currency="EUR",
                            )
                            db.add(portfolio_snapshot)
                            await db.flush()
                            logger.debug(
                                f"Created portfolio snapshot: {portfolio.name} "
                                f"value={metrics.get('total_value', 0)}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot for portfolio {portfolio.id}: {e}")

                await db.commit()

            except Exception as e:
                logger.error(f"Failed to create snapshot for user {user_id}: {e}")
                failed_count += 1

        return {
            "total": len(user_ids),
            "success": success_count,
            "failed": failed_count,
        }


async def _cleanup_old_snapshots_async(days_to_keep: int = 365) -> dict:
    """Delete snapshots older than specified days."""
    async with AsyncSessionLocal() as db:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        result = await db.execute(
            select(func.count(PortfolioSnapshot.id)).where(
                PortfolioSnapshot.snapshot_date < cutoff_date
            )
        )
        count_to_delete = result.scalar()

        if count_to_delete > 0:
            from sqlalchemy import delete
            await db.execute(
                delete(PortfolioSnapshot).where(
                    PortfolioSnapshot.snapshot_date < cutoff_date
                )
            )
            await db.commit()
            logger.info(f"Deleted {count_to_delete} snapshots older than {days_to_keep} days")

        return {"deleted": count_to_delete}


@celery_app.task(name="tasks.create_daily_snapshots")
def create_daily_snapshots() -> dict:
    """Celery task: Create daily portfolio snapshots for all users."""
    return run_async(_create_all_snapshots_async())


@celery_app.task(name="tasks.cleanup_old_snapshots")
def cleanup_old_snapshots(days_to_keep: int = 365) -> dict:
    """Celery task: Delete snapshots older than specified days."""
    return run_async(_cleanup_old_snapshots_async(days_to_keep))


@celery_app.task(name="tasks.create_user_snapshot")
def create_user_snapshot(user_id: str) -> dict:
    """Celery task: Create a snapshot for a specific user (on-demand)."""

    async def _create():
        async with AsyncSessionLocal() as db:
            snapshot = await snapshot_service.create_user_snapshot(db, user_id)
            if snapshot:
                return {
                    "success": True,
                    "snapshot_id": str(snapshot.id),
                    "total_value": float(snapshot.total_value),
                }
            return {"success": False, "error": "No assets found"}

    return run_async(_create())
