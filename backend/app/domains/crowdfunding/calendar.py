import logging
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject, ProjectStatus
from app.domains.crowdfunding.schedule import contractual_schedule
from app.models.calendar_event import CalendarEvent, EventType

logger = logging.getLogger(__name__)

SYNCED_STATUSES = (ProjectStatus.ACTIVE, ProjectStatus.DELAYED)
EVENTS = CalendarEvent.__table__.c


def _at_nine_utc(day: date) -> datetime:
    return datetime.combine(day, time(9, 0), tzinfo=UTC)


def _event(project: CrowdfundingProject, user_id: uuid.UUID, entry: CrowdfundingPaymentSchedule) -> CalendarEvent:
    capital = float(entry.expected_capital)
    interest = float(entry.expected_interest)
    amount = round(capital + interest, 2)
    name = (project.project_name or project.platform)[:150]
    kind = "Remboursement" if capital > 0 else "Coupon"
    return CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title=f"{kind} {name} : +{amount:.2f} €"[:200],
        description=f"{project.platform}\nCapital : {capital:.2f} € + Intérêts nets : {interest:.2f} €",
        event_type=EventType.INTEREST,
        event_date=_at_nine_utc(entry.due_date),
        is_recurring=False,
        amount=amount,
        currency="EUR",
        is_completed=False,
        source_project_id=project.id,
    )


def _upcoming_entries(project: CrowdfundingProject, now: datetime) -> list[CrowdfundingPaymentSchedule]:
    if project.status not in SYNCED_STATUSES or not project.start_date:
        return []
    return [entry for entry in contractual_schedule(project) if _at_nine_utc(entry.due_date) >= now]


def planned_events(project: CrowdfundingProject) -> list[tuple[datetime, float]]:
    """(date, montant) des événements que la synchronisation écrirait pour le projet."""
    entries = _upcoming_entries(project, datetime.now(UTC))
    return [
        (_at_nine_utc(e.due_date), round(float(e.expected_capital) + float(e.expected_interest), 2)) for e in entries
    ]


async def stored_events(db: AsyncSession, project_id: uuid.UUID) -> list[tuple[datetime, float]]:
    """(date, montant) des événements à venir non faits du projet, tels qu'enregistrés."""
    result = await db.execute(
        select(EVENTS.event_date, EVENTS.amount)
        .where(
            EVENTS.source_project_id == project_id,
            EVENTS.is_completed.is_(False),
            EVENTS.event_date >= datetime.now(UTC),
        )
        .order_by(EVENTS.event_date)
    )
    return [(when, round(float(amount or 0), 2)) for when, amount in result.all()]


async def _delete_future_events(db: AsyncSession, project_id: uuid.UUID) -> int:
    result = await db.execute(
        delete(CalendarEvent)
        .where(
            EVENTS.source_project_id == project_id,
            EVENTS.is_completed.is_(False),
            EVENTS.event_date >= datetime.now(UTC),
        )
        .returning(EVENTS.id)
    )
    return len(result.all())


async def sync_project_events(db: AsyncSession, user_id: uuid.UUID, project: CrowdfundingProject) -> int:
    """Remplace au calendrier les échéances contractuelles à venir du projet actif ou en retard ; rend leur nombre."""
    if project.status not in SYNCED_STATUSES:
        return 0
    if not project.start_date:
        logger.warning("Project %s has no start_date, skipping calendar sync", project.id)
        return 0
    now = datetime.now(UTC)
    await _delete_future_events(db, project.id)
    events = [_event(project, user_id, entry) for entry in _upcoming_entries(project, now)]
    db.add_all(events)
    await db.flush()
    logger.info("Synced %d calendar events for project %s", len(events), project.id)
    return len(events)


async def clear_future_events(db: AsyncSession, project_id: uuid.UUID) -> int:
    """Retire du calendrier les échéances à venir d'un projet terminé ou en défaut."""
    deleted = await _delete_future_events(db, project_id)
    logger.info("Cleaned up %d future events for completed project %s", deleted, project_id)
    return deleted


async def upcoming_coupon_income(db: AsyncSession, user_id: uuid.UUID, months_ahead: int = 12) -> list[dict[str, Any]]:
    """Coupons à venir de l'utilisateur sur ``months_ahead`` mois : ``{"month_offset", "amount"}`` par événement."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(EVENTS.event_date, EVENTS.amount)
        .where(
            EVENTS.user_id == user_id,
            EVENTS.source_project_id.is_not(None),
            EVENTS.is_completed.is_(False),
            EVENTS.event_date >= now,
            EVENTS.event_date <= now + relativedelta(months=months_ahead),
            EVENTS.event_type == EventType.INTEREST,
        )
        .order_by(EVENTS.event_date)
    )
    income: list[dict[str, Any]] = []
    for event_date, amount in result.all():
        if amount is None or float(amount) <= 0:
            continue
        offset = (event_date.year - now.year) * 12 + (event_date.month - now.month)
        income.append({"month_offset": max(0, offset), "amount": float(amount)})
    return income


async def complete_closest_event(db: AsyncSession, project_id: uuid.UUID, payment_date: date) -> None:
    """Marque fait l'événement ouvert du projet le plus proche de la date du versement."""
    paid_at = _at_nine_utc(payment_date)
    event_id = await db.scalar(
        select(EVENTS.id)
        .where(EVENTS.source_project_id == project_id, EVENTS.is_completed.is_(False))
        .order_by(func.abs(func.extract("epoch", EVENTS.event_date - paid_at)))
        .limit(1)
    )
    if event_id is None:
        return
    completed = {"is_completed": True, "completed_at": datetime.now(UTC)}
    await db.execute(update(CalendarEvent).where(EVENTS.id == event_id).values(completed))
    logger.info("Marked calendar event %s as completed for project %s", event_id, project_id)
