"""Reconciliation service — schedule generation and payment matching."""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crowdfunding_payment_schedule import CrowdfundingPaymentSchedule
from app.models.crowdfunding_project import CrowdfundingProject, ProjectStatus, RepaymentType

logger = logging.getLogger(__name__)

_MAX_SCHEDULE_MONTHS = 60

# Maps interest_frequency to number of months between payments
_FREQUENCY_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "semi_annual": 6,
    "annual": 12,
}


class ReconciliationService:
    """Generates contractual payment schedules and reconciles repayments."""

    async def populate_initial_schedule(
        self,
        db: AsyncSession,
        project: CrowdfundingProject,
    ) -> int:
        """Generate schedule entries for a project. Idempotent: deletes
        uncompleted entries, preserves completed ones. Returns count created."""
        # Delete uncompleted entries (preserve already-reconciled ones)
        await db.execute(
            delete(CrowdfundingPaymentSchedule).where(
                CrowdfundingPaymentSchedule.project_id == project.id,
                CrowdfundingPaymentSchedule.is_completed.is_(False),
            )
        )

        # Get existing completed due_dates to avoid duplicates
        result = await db.execute(
            select(CrowdfundingPaymentSchedule.due_date).where(
                CrowdfundingPaymentSchedule.project_id == project.id,
                CrowdfundingPaymentSchedule.is_completed.is_(True),
            )
        )
        completed_dates = {row[0] for row in result.all()}

        # Generate new entries
        if project.repayment_type == RepaymentType.AMORTIZABLE:
            entries = self._generate_amortizable(project)
        else:
            entries = self._generate_in_fine(project)

        # Filter out dates already completed
        new_entries = [e for e in entries if e.due_date not in completed_dates]

        for entry in new_entries:
            db.add(entry)

        await db.flush()
        logger.info(
            "Schedule for project %s: %d entries created (%d already completed)",
            project.id,
            len(new_entries),
            len(completed_dates),
        )
        return len(new_entries)

    def _get_net_multiplier(self, project: CrowdfundingProject) -> Decimal:
        """Return (1 - tax_rate/100) to convert gross interest to net."""
        tax_rate = Decimal(str(project.tax_rate)) if project.tax_rate else Decimal("30")
        return Decimal("1") - tax_rate / Decimal("100")

    def _generate_in_fine(self, project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
        """IN_FINE schedule generation based on interest_frequency.

        When delay_months > 0, extra interest-only periods are appended
        and capital moves to the new last entry.
        """
        invested = Decimal(str(project.invested_amount))
        rate = Decimal(str(project.annual_rate)) / Decimal("100")
        contractual_months = int(project.duration_months)
        delay = int(project.delay_months or 0)
        total_months = contractual_months + delay
        frequency = project.interest_frequency or "at_maturity"
        net_mult = self._get_net_multiplier(project)

        if frequency == "at_maturity" or frequency not in _FREQUENCY_MONTHS:
            if not project.estimated_end_date:
                return []
            actual_end = project.estimated_end_date + relativedelta(months=delay)
            total_interest_gross = invested * rate * Decimal(str(total_months)) / Decimal("12")
            total_interest_net = (total_interest_gross * net_mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return [
                CrowdfundingPaymentSchedule(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    due_date=actual_end,
                    expected_capital=invested,
                    expected_interest=total_interest_net,
                )
            ]

        # Periodic interest payments
        if not project.start_date:
            return []

        freq_months = _FREQUENCY_MONTHS[frequency]
        periods_per_year = 12 // freq_months
        periodic_interest_gross = invested * rate / Decimal(str(periods_per_year))
        periodic_interest_net = (periodic_interest_gross * net_mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        num_periods = min(total_months // freq_months, _MAX_SCHEDULE_MONTHS // freq_months)
        entries = []

        for i in range(1, num_periods + 1):
            due = project.start_date + relativedelta(months=freq_months * i)
            is_last = i == num_periods
            entries.append(
                CrowdfundingPaymentSchedule(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    due_date=due,
                    expected_capital=invested if is_last else Decimal("0"),
                    expected_interest=periodic_interest_net,
                )
            )

        return entries

    def _generate_amortizable(self, project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
        """AMORTIZABLE: monthly interest, capital on last month."""
        if not project.start_date:
            return []

        invested = Decimal(str(project.invested_amount))
        rate = Decimal(str(project.annual_rate)) / Decimal("100")
        delay = int(project.delay_months or 0)
        months = min(int(project.duration_months) + delay, _MAX_SCHEDULE_MONTHS)
        net_mult = self._get_net_multiplier(project)

        monthly_interest = (invested * rate / Decimal("12") * net_mult).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        entries = []
        for m in range(1, months + 1):
            due = project.start_date + relativedelta(months=m)
            is_last = m == months
            entries.append(
                CrowdfundingPaymentSchedule(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    due_date=due,
                    expected_capital=invested if is_last else Decimal("0"),
                    expected_interest=monthly_interest,
                )
            )

        return entries

    async def reconcile_repayment(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        repayment_id: uuid.UUID,
        payment_date: date,
    ) -> CrowdfundingPaymentSchedule | None:
        """Find closest uncompleted schedule entry and mark it completed."""
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

        # Find closest by date distance
        closest = min(entries, key=lambda e: abs((e.due_date - payment_date).days))
        closest.is_completed = True
        closest.completed_at = datetime.now(timezone.utc)
        closest.repayment_id = repayment_id

        return closest

    async def unreconcile_repayment(
        self,
        db: AsyncSession,
        repayment_id: uuid.UUID,
    ) -> None:
        """Unmark schedule entry when a repayment is deleted."""
        result = await db.execute(
            select(CrowdfundingPaymentSchedule).where(
                CrowdfundingPaymentSchedule.repayment_id == repayment_id,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.is_completed = False
            entry.completed_at = None
            entry.repayment_id = None

    async def get_schedule_for_project(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
    ) -> list[CrowdfundingPaymentSchedule]:
        """Return all schedule entries ordered by due_date."""
        result = await db.execute(
            select(CrowdfundingPaymentSchedule)
            .where(CrowdfundingPaymentSchedule.project_id == project_id)
            .order_by(CrowdfundingPaymentSchedule.due_date)
        )
        return list(result.scalars().all())

    async def get_overdue_entries(
        self,
        db: AsyncSession,
        grace_days: int = 5,
    ) -> list[tuple[CrowdfundingPaymentSchedule, CrowdfundingProject]]:
        """Find uncompleted entries past grace period for ACTIVE projects."""
        from datetime import timedelta

        cutoff = date.today() - timedelta(days=grace_days)

        result = await db.execute(
            select(CrowdfundingPaymentSchedule, CrowdfundingProject)
            .join(
                CrowdfundingProject,
                CrowdfundingPaymentSchedule.project_id == CrowdfundingProject.id,
            )
            .where(
                CrowdfundingPaymentSchedule.is_completed.is_(False),
                CrowdfundingPaymentSchedule.due_date < cutoff,
                CrowdfundingProject.status == ProjectStatus.ACTIVE,
            )
        )
        return list(result.all())


reconciliation_service = ReconciliationService()
