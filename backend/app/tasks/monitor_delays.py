"""Celery task to detect overdue crowdfunding payment schedules."""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.monitor_delays.check_crowdfunding_delays")
def check_crowdfunding_delays():
    """Detect overdue schedules (due_date < now - 5 days).
    Sets project.status = DELAYED and creates a notification."""

    async def _check():
        from app.core.database import AsyncSessionLocal
        from app.models.asset import Asset
        from app.models.notification import Notification, NotificationPriority, NotificationType
        from app.models.portfolio import Portfolio
        from app.services.reconciliation_service import reconciliation_service

        async with AsyncSessionLocal() as db:
            rows = await reconciliation_service.get_overdue_entries(db, grace_days=5)

            # Group by project to avoid duplicate status updates
            delayed_projects: dict = {}
            for entry, project in rows:
                if project.id not in delayed_projects:
                    delayed_projects[project.id] = (project, entry)

            count = 0
            for project_id, (project, entry) in delayed_projects.items():
                project.status = "delayed"

                # Find user_id via asset -> portfolio
                asset = await db.get(Asset, project.asset_id)
                if not asset:
                    continue
                portfolio = await db.get(Portfolio, asset.portfolio_id)
                if not portfolio:
                    continue

                name = project.project_name or project.platform
                notification = Notification(
                    user_id=portfolio.user_id,
                    type=NotificationType.SYSTEM,
                    title=f"Retard de paiement : {name}",
                    message=(
                        f"L'echeance du {entry.due_date.strftime('%d/%m/%Y')} "
                        f"({float(entry.expected_interest):.2f} EUR interets"
                        f"{f' + {float(entry.expected_capital):.2f} EUR capital' if entry.expected_capital > 0 else ''}"
                        f") n'a pas ete recu pour le projet {name} ({project.platform})."
                    ),
                    priority=NotificationPriority.HIGH,
                    reference_type="crowdfunding_project",
                    reference_id=project.id,
                )
                db.add(notification)
                count += 1

            await db.commit()
            return {"delayed_projects": count, "overdue_entries": len(rows)}

    result = run_async(_check())
    logger.info(
        "Delay check: %d projects set to DELAYED, %d overdue entries found",
        result["delayed_projects"],
        result["overdue_entries"],
    )
    return result
