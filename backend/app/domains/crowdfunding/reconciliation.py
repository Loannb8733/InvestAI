import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Row, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject, ProjectStatus
from app.domains.crowdfunding.schedule import contractual_schedule

logger = logging.getLogger(__name__)

AMOUNT_TOLERANCE = Decimal("0.01")


async def refresh_schedule(db: AsyncSession, project: CrowdfundingProject) -> int:
    """Régénère les échéances non soldées du projet en gardant les soldées ; rend le nombre d'échéances créées."""
    await db.execute(
        delete(CrowdfundingPaymentSchedule).where(
            CrowdfundingPaymentSchedule.project_id == project.id,
            CrowdfundingPaymentSchedule.is_completed.is_(False),
        )
    )
    result = await db.execute(
        select(CrowdfundingPaymentSchedule.due_date).where(
            CrowdfundingPaymentSchedule.project_id == project.id,
            CrowdfundingPaymentSchedule.is_completed.is_(True),
        )
    )
    completed = {row[0] for row in result.all()}
    entries = [entry for entry in contractual_schedule(project) if entry.due_date not in completed]
    for entry in entries:
        db.add(entry)
    await db.flush()
    logger.info(
        "Schedule for project %s: %d entries created (%d already completed)", project.id, len(entries), len(completed)
    )
    return len(entries)


def match_score(entry: CrowdfundingPaymentSchedule, payment_date: date, amount: Decimal | None) -> tuple[int, int]:
    """(le montant colle à 1 % près ou non, écart en jours) : la plus petite valeur désigne l'échéance soldée."""
    days = abs((entry.due_date - payment_date).days)
    if amount is None:
        return (0, days)
    expected = (entry.expected_capital or Decimal("0")) + (entry.expected_interest or Decimal("0"))
    if expected <= 0:
        return (1, days)
    gap = abs(expected - Decimal(amount)) / expected
    return (0 if gap <= AMOUNT_TOLERANCE else 1, days)


async def reconcile_repayment(
    db: AsyncSession,
    project_id: uuid.UUID,
    repayment_id: uuid.UUID,
    payment_date: date,
    amount: Decimal | None = None,
) -> CrowdfundingPaymentSchedule | None:
    """Marque soldée l'échéance ouverte que le versement désigne, par le montant puis par la date."""
    result = await db.execute(
        select(CrowdfundingPaymentSchedule)
        .where(
            CrowdfundingPaymentSchedule.project_id == project_id,
            CrowdfundingPaymentSchedule.is_completed.is_(False),
        )
        .order_by(CrowdfundingPaymentSchedule.due_date)
    )
    entries = result.scalars().all()
    if not entries:
        return None
    closest = min(entries, key=lambda entry: match_score(entry, payment_date, amount))
    closest.is_completed = True
    closest.completed_at = datetime.now(UTC)
    closest.repayment_id = repayment_id
    return closest


async def unreconcile_repayment(db: AsyncSession, repayment_id: uuid.UUID) -> None:
    """Rouvre l'échéance soldée par ce versement."""
    result = await db.execute(
        select(CrowdfundingPaymentSchedule).where(CrowdfundingPaymentSchedule.repayment_id == repayment_id)
    )
    entry = result.scalar_one_or_none()
    if entry:
        entry.is_completed = False
        entry.completed_at = None
        entry.repayment_id = None


async def overdue_entries(
    db: AsyncSession, grace_days: int = 5
) -> list[Row[CrowdfundingPaymentSchedule, CrowdfundingProject]]:
    """Échéances non soldées, échues depuis plus de ``grace_days`` jours, des projets actifs."""
    cutoff = date.today() - timedelta(days=grace_days)
    result = await db.execute(
        select(CrowdfundingPaymentSchedule, CrowdfundingProject)
        .join(CrowdfundingProject, CrowdfundingPaymentSchedule.project_id == CrowdfundingProject.id)
        .where(
            CrowdfundingPaymentSchedule.is_completed.is_(False),
            CrowdfundingPaymentSchedule.due_date < cutoff,
            CrowdfundingProject.status == ProjectStatus.ACTIVE,
        )
    )
    return list(result.all())
