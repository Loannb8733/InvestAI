"""Service for syncing crowdfunding project events to the calendar."""

import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import List

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import CalendarEvent, EventType
from app.models.crowdfunding_project import CrowdfundingProject, ProjectStatus, RepaymentType

logger = logging.getLogger(__name__)

# Max months of events to generate (cap for very long projects)
_MAX_EVENT_MONTHS = 60


def _date_to_utc(d: date) -> datetime:
    """Convert a plain date to a timezone-aware UTC datetime at 09:00."""
    return datetime.combine(d, time(9, 0), tzinfo=timezone.utc)


class CrowdfundingCalendarService:
    """Generates and manages calendar events for crowdfunding coupons."""

    async def sync_events_for_project(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: CrowdfundingProject,
    ) -> int:
        """Idempotent sync: delete future uncompleted events, then regenerate.

        Returns the number of events created.
        """
        if project.status not in (ProjectStatus.ACTIVE, ProjectStatus.DELAYED):
            return 0
        if not project.start_date:
            logger.warning("Project %s has no start_date, skipping calendar sync", project.id)
            return 0

        now = datetime.now(timezone.utc)

        # Delete future uncompleted events for this project
        await db.execute(
            delete(CalendarEvent).where(
                CalendarEvent.source_project_id == project.id,
                CalendarEvent.is_completed == False,  # noqa: E712
                CalendarEvent.event_date >= now,
            )
        )

        # Generate new events
        if project.repayment_type == RepaymentType.IN_FINE:
            events = self._generate_events_in_fine(project, user_id)
        else:
            events = self._generate_events_amortizable(project, user_id)

        # Filter: only future events
        events = [e for e in events if e.event_date >= now]

        for event in events:
            db.add(event)

        await db.flush()
        logger.info("Synced %d calendar events for project %s", len(events), project.id)
        return len(events)

    async def cleanup_completed_project(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
    ) -> int:
        """Delete future uncompleted events when project is completed/defaulted."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            delete(CalendarEvent)
            .where(
                CalendarEvent.source_project_id == project_id,
                CalendarEvent.is_completed == False,  # noqa: E712
                CalendarEvent.event_date >= now,
            )
            .returning(CalendarEvent.id)
        )
        deleted = len(result.all())
        logger.info("Cleaned up %d future events for completed project %s", deleted, project_id)
        return deleted

    async def get_upcoming_coupon_income(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        months_ahead: int = 12,
    ) -> List[dict]:
        """Return upcoming coupon income grouped by month offset.

        Returns list of {month_offset: int, amount: float}.
        """
        now = datetime.now(timezone.utc)
        cutoff = now + relativedelta(months=months_ahead)

        result = await db.execute(
            select(CalendarEvent.event_date, CalendarEvent.amount)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.source_project_id.is_not(None),
                CalendarEvent.is_completed == False,  # noqa: E712
                CalendarEvent.event_date >= now,
                CalendarEvent.event_date <= cutoff,
                CalendarEvent.event_type == EventType.INTEREST,
            )
            .order_by(CalendarEvent.event_date)
        )
        rows = result.all()

        income: List[dict] = []
        for event_date, amount in rows:
            if amount is None or float(amount) <= 0:
                continue
            # Calculate month offset from now
            months_diff = (event_date.year - now.year) * 12 + (event_date.month - now.month)
            income.append({"month_offset": max(0, months_diff), "amount": float(amount)})

        return income

    # ──────────────────── Private generators ────────────────────

    def _generate_events_in_fine(
        self,
        project: CrowdfundingProject,
        user_id: uuid.UUID,
    ) -> List[CalendarEvent]:
        """IN_FINE: single event at maturity with capital + all interest."""
        if not project.estimated_end_date:
            return []

        invested = float(project.invested_amount)
        rate = float(project.annual_rate) / 100
        months = int(project.duration_months)
        total_interest = invested * rate * months / 12
        total_amount = round(invested + total_interest, 2)

        name = (project.project_name or project.platform)[:150]
        title = f"Coupon {name} : +{total_amount:.2f} €"

        return [
            CalendarEvent(
                id=uuid.uuid4(),
                user_id=user_id,
                title=title[:200],
                description=(
                    f"Remboursement in fine - {project.platform}\n"
                    f"Capital : {invested:.2f} € + Intérêts : {total_interest:.2f} €\n"
                    f"TRI : {float(project.annual_rate):.1f}% sur {months} mois"
                ),
                event_type=EventType.INTEREST,
                event_date=_date_to_utc(project.estimated_end_date),
                is_recurring=False,
                amount=total_amount,
                currency="EUR",
                is_completed=False,
                source_project_id=project.id,
            )
        ]

    def _generate_events_amortizable(
        self,
        project: CrowdfundingProject,
        user_id: uuid.UUID,
    ) -> List[CalendarEvent]:
        """AMORTIZABLE: monthly interest events + capital return at end."""
        if not project.start_date:
            return []

        invested = float(project.invested_amount)
        rate = float(project.annual_rate) / 100
        months = min(int(project.duration_months), _MAX_EVENT_MONTHS)
        monthly_interest = round(invested * rate / 12, 2)

        name = (project.project_name or project.platform)[:150]
        events: List[CalendarEvent] = []

        for m in range(1, months + 1):
            event_date = project.start_date + relativedelta(months=m)
            is_last = m == months
            amount = round(monthly_interest + (invested if is_last else 0), 2)

            if is_last:
                title = f"Coupon final {name} : +{amount:.2f} €"
                desc = (
                    f"Dernier versement - {project.platform}\n"
                    f"Intérêts : {monthly_interest:.2f} € + Capital : {invested:.2f} €\n"
                    f"TRI : {float(project.annual_rate):.1f}%"
                )
            else:
                title = f"Coupon {name} : +{amount:.2f} €"
                desc = (
                    f"Versement mensuel - {project.platform}\n"
                    f"Intérêts : {monthly_interest:.2f} € (mois {m}/{months})\n"
                    f"TRI : {float(project.annual_rate):.1f}%"
                )

            events.append(
                CalendarEvent(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    title=title[:200],
                    description=desc,
                    event_type=EventType.INTEREST,
                    event_date=_date_to_utc(event_date),
                    is_recurring=False,
                    amount=amount,
                    currency="EUR",
                    is_completed=False,
                    source_project_id=project.id,
                )
            )

        return events


crowdfunding_calendar_service = CrowdfundingCalendarService()
