"""Data cleanup tasks for database maintenance."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, delete, func, and_

from app.core.database import AsyncSessionLocal


def run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
from app.models.notification import Notification
from app.models.prediction_log import PredictionLog
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _cleanup_old_notifications_async(days_to_keep: int = 30) -> dict:
    """Delete read notifications older than specified days."""
    async with AsyncSessionLocal() as db:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        # Count notifications to delete
        count_result = await db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.read == True,
                    Notification.created_at < cutoff_date,
                )
            )
        )
        count_to_delete = count_result.scalar()

        if count_to_delete > 0:
            await db.execute(
                delete(Notification).where(
                    and_(
                        Notification.read == True,
                        Notification.created_at < cutoff_date,
                    )
                )
            )
            await db.commit()
            logger.info(f"Deleted {count_to_delete} old read notifications (older than {days_to_keep} days)")

        return {"deleted_notifications": count_to_delete}


async def _cleanup_old_predictions_async(days_to_keep: int = 90) -> dict:
    """Delete old prediction records older than specified days."""
    async with AsyncSessionLocal() as db:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        # Count predictions to delete
        count_result = await db.execute(
            select(func.count(PredictionLog.id)).where(
                PredictionLog.created_at < cutoff_date
            )
        )
        count_to_delete = count_result.scalar()

        if count_to_delete > 0:
            await db.execute(
                delete(PredictionLog).where(
                    PredictionLog.created_at < cutoff_date
                )
            )
            await db.commit()
            logger.info(f"Deleted {count_to_delete} old predictions (older than {days_to_keep} days)")

        return {"deleted_predictions": count_to_delete}


async def _cleanup_duplicate_transactions_async() -> dict:
    """Find and remove duplicate transactions (same external_id)."""
    from app.models.transaction import Transaction

    async with AsyncSessionLocal() as db:
        # Find duplicate external_ids
        dup_query = select(
            Transaction.external_id,
            func.count(Transaction.id).label("cnt")
        ).where(
            Transaction.external_id.isnot(None)
        ).group_by(
            Transaction.external_id
        ).having(
            func.count(Transaction.id) > 1
        )

        result = await db.execute(dup_query)
        duplicates = result.fetchall()

        deleted_count = 0
        for dup in duplicates:
            ext_id = dup.external_id
            # Get all transactions with this external_id, keep the oldest
            trans_result = await db.execute(
                select(Transaction).where(
                    Transaction.external_id == ext_id
                ).order_by(Transaction.created_at.asc())
            )
            transactions = trans_result.scalars().all()

            # Delete all but the first one
            for tx in transactions[1:]:
                await db.delete(tx)
                deleted_count += 1

        if deleted_count > 0:
            await db.commit()
            logger.info(f"Deleted {deleted_count} duplicate transactions")

        return {"deleted_duplicates": deleted_count}


async def _validate_portfolio_consistency_async() -> dict:
    """Validate that asset quantities match transaction sums."""
    from app.models.asset import Asset
    from app.models.transaction import Transaction, TransactionType
    from app.models.portfolio import Portfolio

    async with AsyncSessionLocal() as db:
        # Get all assets with their calculated quantities from transactions
        query = select(
            Asset.id,
            Asset.symbol,
            Asset.quantity,
            Portfolio.name.label("portfolio_name"),
        ).join(Portfolio, Asset.portfolio_id == Portfolio.id)

        result = await db.execute(query)
        assets = result.fetchall()

        inconsistencies = []
        for asset in assets:
            # Calculate expected quantity from transactions
            calc_result = await db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            func.case(
                                (Transaction.transaction_type.in_([
                                    TransactionType.BUY,
                                    TransactionType.TRANSFER_IN,
                                    TransactionType.CONVERSION_IN,
                                    TransactionType.AIRDROP,
                                    TransactionType.STAKING_REWARD,
                                ]), Transaction.quantity),
                                else_=0
                            )
                        ), 0
                    ) - func.coalesce(
                        func.sum(
                            func.case(
                                (Transaction.transaction_type.in_([
                                    TransactionType.SELL,
                                    TransactionType.TRANSFER_OUT,
                                    TransactionType.CONVERSION_OUT,
                                ]), Transaction.quantity),
                                else_=0
                            )
                        ), 0
                    )
                ).where(Transaction.asset_id == asset.id)
            )
            calc_qty = float(calc_result.scalar() or 0)
            stored_qty = float(asset.quantity)

            if abs(calc_qty - stored_qty) > 0.00001:
                inconsistencies.append({
                    "asset_id": str(asset.id),
                    "symbol": asset.symbol,
                    "portfolio": asset.portfolio_name,
                    "stored_qty": stored_qty,
                    "calculated_qty": calc_qty,
                    "difference": stored_qty - calc_qty,
                })

        if inconsistencies:
            logger.warning(f"Found {len(inconsistencies)} portfolio inconsistencies")
            for inc in inconsistencies[:10]:  # Log first 10
                logger.warning(
                    f"  {inc['portfolio']}/{inc['symbol']}: "
                    f"stored={inc['stored_qty']:.8f} calc={inc['calculated_qty']:.8f}"
                )

        return {
            "total_assets_checked": len(assets),
            "inconsistencies_found": len(inconsistencies),
            "details": inconsistencies[:20],  # Return first 20
        }


async def _run_all_cleanup_async() -> dict:
    """Run all cleanup tasks."""
    results = {}

    try:
        results["notifications"] = await _cleanup_old_notifications_async()
    except Exception as e:
        logger.error(f"Notification cleanup failed: {e}")
        results["notifications"] = {"error": str(e)}

    try:
        results["predictions"] = await _cleanup_old_predictions_async()
    except Exception as e:
        logger.error(f"PredictionLog cleanup failed: {e}")
        results["predictions"] = {"error": str(e)}

    try:
        results["duplicates"] = await _cleanup_duplicate_transactions_async()
    except Exception as e:
        logger.error(f"Duplicate cleanup failed: {e}")
        results["duplicates"] = {"error": str(e)}

    return results


# === Celery Tasks ===

@celery_app.task(name="tasks.cleanup_old_notifications")
def cleanup_old_notifications(days_to_keep: int = 30) -> dict:
    """Celery task: Delete old read notifications."""
    return run_async(_cleanup_old_notifications_async(days_to_keep))


@celery_app.task(name="tasks.cleanup_old_predictions")
def cleanup_old_predictions(days_to_keep: int = 90) -> dict:
    """Celery task: Delete old prediction records."""
    return run_async(_cleanup_old_predictions_async(days_to_keep))


@celery_app.task(name="tasks.cleanup_duplicate_transactions")
def cleanup_duplicate_transactions() -> dict:
    """Celery task: Remove duplicate transactions."""
    return run_async(_cleanup_duplicate_transactions_async())


@celery_app.task(name="tasks.validate_portfolio_consistency")
def validate_portfolio_consistency() -> dict:
    """Celery task: Validate portfolio quantities match transactions."""
    return run_async(_validate_portfolio_consistency_async())


@celery_app.task(name="tasks.run_weekly_cleanup")
def run_weekly_cleanup() -> dict:
    """Celery task: Run all cleanup tasks."""
    return run_async(_run_all_cleanup_async())
