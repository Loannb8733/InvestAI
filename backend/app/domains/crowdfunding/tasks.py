import logging
import uuid
from typing import Any

from app.core.db.session import session_factory
from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject, ProjectStatus
from app.domains.crowdfunding.reconciliation import overdue_entries
from app.domains.crowdfunding.repository import project_owner
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

GRACE_DAYS = 5


def _delay_message(project: CrowdfundingProject, entry: CrowdfundingPaymentSchedule, name: str) -> str:
    capital = f" + {float(entry.expected_capital):.2f} EUR capital" if entry.expected_capital > 0 else ""
    return (
        f"L'echeance du {entry.due_date.strftime('%d/%m/%Y')} "
        f"({float(entry.expected_interest):.2f} EUR interets{capital}"
        f") n'a pas ete recu pour le projet {name} ({project.platform})."
    )


async def _flag_delays() -> dict[str, int]:
    async with session_factory() as db:
        rows = await overdue_entries(db, grace_days=GRACE_DAYS)
        first_overdue: dict[uuid.UUID, tuple[CrowdfundingProject, CrowdfundingPaymentSchedule]] = {}
        for entry, project in rows:
            first_overdue.setdefault(project.id, (project, entry))
        count = 0
        for project, entry in first_overdue.values():
            project.status = ProjectStatus.DELAYED
            user_id = await project_owner(db, project)
            if user_id is None:
                continue
            name = project.project_name or project.platform
            db.add(
                Notification(
                    user_id=user_id,
                    type=NotificationType.SYSTEM,
                    title=f"Retard de paiement : {name}",
                    message=_delay_message(project, entry, name),
                    priority=NotificationPriority.HIGH,
                    reference_type="crowdfunding_project",
                    reference_id=project.id,
                )
            )
            count += 1
        await db.commit()
        return {"delayed_projects": count, "overdue_entries": len(rows)}


@celery_app.task(name="app.domains.crowdfunding.tasks.check_crowdfunding_delays")  # type: ignore[untyped-decorator]
def check_crowdfunding_delays() -> dict[str, Any]:
    """Passe en retard les projets actifs à échéance impayée passé 5 jours de grâce, et prévient leur propriétaire."""
    result: dict[str, Any] = run_async(_flag_delays())
    logger.info(
        "Delay check: %d projects set to DELAYED, %d overdue entries found",
        result["delayed_projects"],
        result["overdue_entries"],
    )
    return result
