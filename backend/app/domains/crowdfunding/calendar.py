import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding.models import CrowdfundingProject, ProjectStatus, RepaymentType
from app.models.calendar_event import CalendarEvent, EventType

logger = logging.getLogger(__name__)

MAX_EVENT_MONTHS = 60
SYNCED_STATUSES = (ProjectStatus.ACTIVE, ProjectStatus.DELAYED)
EVENTS = CalendarEvent.__table__.c


@dataclass
class _Coupon:
    day: date
    title: str
    description: str
    amount: float

    @property
    def at(self) -> datetime:
        return datetime.combine(self.day, time(9, 0), tzinfo=UTC)


def _in_fine_coupons(project: CrowdfundingProject) -> list[_Coupon]:
    if not project.estimated_end_date:
        return []
    invested = float(project.invested_amount)
    rate = float(project.annual_rate) / 100
    months = int(project.duration_months)
    interest = invested * rate * months / 12
    total = round(invested + interest, 2)
    name = (project.project_name or project.platform)[:150]
    description = (
        f"Remboursement in fine - {project.platform}\n"
        f"Capital : {invested:.2f} € + Intérêts : {interest:.2f} €\n"
        f"TRI : {float(project.annual_rate):.1f}% sur {months} mois"
    )
    return [_Coupon(project.estimated_end_date, f"Coupon {name} : +{total:.2f} €", description, total)]


def _amortizable_coupon(project: CrowdfundingProject, start: date, month: int, months: int, coupon: float) -> _Coupon:
    invested = float(project.invested_amount)
    name = (project.project_name or project.platform)[:150]
    rate = f"TRI : {float(project.annual_rate):.1f}%"
    day = start + relativedelta(months=month)
    if month == months:
        amount = round(coupon + invested, 2)
        description = (
            f"Dernier versement - {project.platform}\nIntérêts : {coupon:.2f} € + Capital : {invested:.2f} €\n{rate}"
        )
        return _Coupon(day, f"Coupon final {name} : +{amount:.2f} €", description, amount)
    description = f"Versement mensuel - {project.platform}\nIntérêts : {coupon:.2f} € (mois {month}/{months})\n{rate}"
    return _Coupon(day, f"Coupon {name} : +{coupon:.2f} €", description, coupon)


def _amortizable_coupons(project: CrowdfundingProject) -> list[_Coupon]:
    start = project.start_date
    if not start:
        return []
    months = min(int(project.duration_months), MAX_EVENT_MONTHS)
    coupon = round(float(project.invested_amount) * (float(project.annual_rate) / 100) / 12, 2)
    return [_amortizable_coupon(project, start, month, months, coupon) for month in range(1, months + 1)]


def _event(project: CrowdfundingProject, user_id: uuid.UUID, coupon: _Coupon) -> CalendarEvent:
    return CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title=coupon.title[:200],
        description=coupon.description,
        event_type=EventType.INTEREST,
        event_date=coupon.at,
        is_recurring=False,
        amount=coupon.amount,
        currency="EUR",
        is_completed=False,
        source_project_id=project.id,
    )


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
    """Remplace les échéances à venir du projet actif ou en retard dans le calendrier ; rend le nombre créé."""
    if project.status not in SYNCED_STATUSES:
        return 0
    if not project.start_date:
        logger.warning("Project %s has no start_date, skipping calendar sync", project.id)
        return 0
    now = datetime.now(UTC)
    await _delete_future_events(db, project.id)
    if project.repayment_type == RepaymentType.IN_FINE:
        coupons = _in_fine_coupons(project)
    else:
        coupons = _amortizable_coupons(project)
    events = [_event(project, user_id, coupon) for coupon in coupons if coupon.at >= now]
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
    paid_at = datetime.combine(payment_date, time(9, 0), tzinfo=UTC)
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
