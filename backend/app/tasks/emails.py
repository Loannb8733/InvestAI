"""Email tasks for sending notifications and reports."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from sqlalchemy import select, and_

from app.core.database import AsyncSessionLocal


def run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.notification import Notification
from app.models.alert import Alert
from app.services.email_service import email_service
from app.services.metrics_service import metrics_service
from app.services.snapshot_service import snapshot_service
from app.services.report_service import report_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _send_alert_email_async(
    user_id: str,
    alert_name: str,
    asset_symbol: str,
    current_price: float,
    target_price: float,
    condition: str,
) -> bool:
    """Send alert notification email to user."""
    if not email_service.is_configured:
        return False

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.email:
            return False

        return await email_service.send_alert_notification(
            to_email=user.email,
            alert_name=alert_name,
            asset_symbol=asset_symbol,
            current_price=current_price,
            target_price=target_price,
            condition=condition,
        )


async def _send_weekly_reports_async() -> dict:
    """Send weekly reports to all users with portfolios."""
    if not email_service.is_configured:
        logger.warning("Email not configured, skipping weekly reports")
        return {"sent": 0, "failed": 0, "skipped": "email_not_configured"}

    async with AsyncSessionLocal() as db:
        # Get all users with portfolios
        result = await db.execute(
            select(User).where(
                User.id.in_(select(Portfolio.user_id).distinct())
            )
        )
        users = result.scalars().all()

        sent_count = 0
        failed_count = 0

        for user in users:
            try:
                # Get current metrics
                metrics = await metrics_service.get_user_dashboard_metrics(db, str(user.id))

                if metrics["total_value"] == 0:
                    continue

                # Get historical data for week comparison
                history = await snapshot_service.get_historical_values(
                    db, str(user.id), days=7
                )

                week_start_value = history[0]["value"] if history else metrics["total_value"]
                week_change = metrics["total_value"] - week_start_value
                week_change_pct = (week_change / week_start_value * 100) if week_start_value > 0 else 0

                # Get top/worst performers (simplified - would need asset-level history)
                top_performers = []
                worst_performers = []

                success = await email_service.send_weekly_report(
                    to_email=user.email,
                    user_name=f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split("@")[0],
                    total_value=metrics["total_value"],
                    total_invested=metrics["total_invested"],
                    week_change=week_change,
                    week_change_pct=week_change_pct,
                    top_performers=top_performers,
                    worst_performers=worst_performers,
                )

                if success:
                    sent_count += 1
                    logger.info(f"Weekly report sent to {user.email}")
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send weekly report to {user.email}: {e}")
                failed_count += 1

        return {"sent": sent_count, "failed": failed_count}


async def _send_monthly_reports_async() -> dict:
    """Send monthly reports to all users with portfolios."""
    if not email_service.is_configured:
        logger.warning("Email not configured, skipping monthly reports")
        return {"sent": 0, "failed": 0, "skipped": "email_not_configured"}

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(
                User.id.in_(select(Portfolio.user_id).distinct())
            )
        )
        users = result.scalars().all()

        sent_count = 0
        failed_count = 0

        for user in users:
            try:
                metrics = await metrics_service.get_user_dashboard_metrics(db, str(user.id))

                if metrics["total_value"] == 0:
                    continue

                # Get historical data for month comparison
                history = await snapshot_service.get_historical_values(
                    db, str(user.id), days=30
                )

                month_start_value = history[0]["value"] if history else metrics["total_value"]
                month_change = metrics["total_value"] - month_start_value
                month_change_pct = (month_change / month_start_value * 100) if month_start_value > 0 else 0

                # YTD calculation
                ytd_history = await snapshot_service.get_historical_values(
                    db, str(user.id), days=365
                )
                jan1_value = metrics["total_invested"]  # Fallback
                if ytd_history:
                    # Find value closest to Jan 1
                    for h in ytd_history:
                        if h["full_date"][:10] >= f"{datetime.now().year}-01-01":
                            jan1_value = h["value"]
                            break

                ytd_change_pct = ((metrics["total_value"] - jan1_value) / jan1_value * 100) if jan1_value > 0 else 0

                # Get allocation
                allocation = []
                if "assets" in metrics:
                    total = metrics["total_value"]
                    for asset in metrics["assets"]:
                        value = asset.get("current_value", 0)
                        allocation.append({
                            "symbol": asset.get("symbol", "?"),
                            "allocation_pct": (value / total * 100) if total > 0 else 0,
                            "value": value,
                        })
                    allocation.sort(key=lambda x: x["value"], reverse=True)

                # Generate PDF report
                pdf_content = None
                try:
                    report_data = await report_service.get_performance_report(db, str(user.id))
                    pdf_content = report_service.generate_performance_pdf(report_data)
                except Exception as e:
                    logger.warning(f"Could not generate PDF for {user.email}: {e}")

                success = await email_service.send_monthly_report(
                    to_email=user.email,
                    user_name=f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split("@")[0],
                    total_value=metrics["total_value"],
                    total_invested=metrics["total_invested"],
                    month_change=month_change,
                    month_change_pct=month_change_pct,
                    ytd_change_pct=ytd_change_pct,
                    allocation=allocation,
                    pdf_content=pdf_content,
                )

                if success:
                    sent_count += 1
                    logger.info(f"Monthly report sent to {user.email}")
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send monthly report to {user.email}: {e}")
                failed_count += 1

        return {"sent": sent_count, "failed": failed_count}


async def _send_daily_digest_async() -> dict:
    """Send daily digest to users with recent activity."""
    if not email_service.is_configured:
        return {"sent": 0, "failed": 0, "skipped": "email_not_configured"}

    async with AsyncSessionLocal() as db:
        yesterday = datetime.utcnow() - timedelta(days=1)

        # Get users with notifications in last 24h
        result = await db.execute(
            select(User).where(
                User.id.in_(
                    select(Notification.user_id).where(
                        Notification.created_at >= yesterday
                    ).distinct()
                )
            )
        )
        users = result.scalars().all()

        sent_count = 0
        failed_count = 0

        for user in users:
            try:
                # Get recent notifications
                notif_result = await db.execute(
                    select(Notification).where(
                        and_(
                            Notification.user_id == user.id,
                            Notification.created_at >= yesterday,
                        )
                    ).order_by(Notification.created_at.desc())
                )
                notifications = notif_result.scalars().all()

                if not notifications:
                    continue

                # Build alerts list
                alerts_triggered = []
                for n in notifications:
                    if "alert" in n.type.lower():
                        alerts_triggered.append({
                            "symbol": n.title.split()[-1] if n.title else "?",
                            "message": n.message,
                        })

                # Get insights (simplified)
                insights = []
                for n in notifications:
                    if "insight" in n.type.lower() or "tip" in n.type.lower():
                        insights.append(n.message)

                if alerts_triggered or insights:
                    success = await email_service.send_digest(
                        to_email=user.email,
                        user_name=f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split("@")[0],
                        alerts_triggered=alerts_triggered,
                        predictions=[],
                        insights=insights,
                    )

                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send digest to {user.email}: {e}")
                failed_count += 1

        return {"sent": sent_count, "failed": failed_count}


# === Celery Tasks ===

@celery_app.task(name="tasks.send_alert_email")
def send_alert_email(
    user_id: str,
    alert_name: str,
    asset_symbol: str,
    current_price: float,
    target_price: float,
    condition: str,
) -> bool:
    """Celery task: Send alert notification email."""
    return run_async(
        _send_alert_email_async(user_id, alert_name, asset_symbol, current_price, target_price, condition)
    )


@celery_app.task(name="tasks.send_weekly_reports")
def send_weekly_reports() -> dict:
    """Celery task: Send weekly performance reports to all users."""
    return run_async(_send_weekly_reports_async())


@celery_app.task(name="tasks.send_monthly_reports")
def send_monthly_reports() -> dict:
    """Celery task: Send monthly performance reports to all users."""
    return run_async(_send_monthly_reports_async())


@celery_app.task(name="tasks.send_daily_digest")
def send_daily_digest() -> dict:
    """Celery task: Send daily digest to users with recent notifications."""
    return run_async(_send_daily_digest_async())
