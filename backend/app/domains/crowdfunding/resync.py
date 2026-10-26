from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding import calendar
from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject
from app.domains.crowdfunding.reconciliation import refresh_schedule
from app.domains.crowdfunding.repository import project_owner
from app.domains.crowdfunding.schedule import contractual_schedule

CENT = Decimal("0.01")
DOUBLE_CAPITAL = "le capital déjà soldé par l'ancien échéancier serait attendu une seconde fois"
NO_OWNER = "propriétaire introuvable (actif ou portefeuille supprimé)"

Installment = tuple[date, Decimal, Decimal]


@dataclass
class ResyncPlan:
    """Ce que la resynchronisation changerait pour un projet ; ``blocker`` dit pourquoi elle s'abstiendrait."""

    project: CrowdfundingProject
    open_before: list[Installment]
    open_after: list[Installment]
    events_before: list[tuple[datetime, float]]
    events_after: list[tuple[datetime, float]]
    blocker: str | None = None

    @property
    def changed(self) -> bool:
        """Vrai si l'échéancier ouvert ou le calendrier à venir diffèrent du calcul actuel."""
        return self.open_before != self.open_after or self.events_before != self.events_after


def _installment(entry: CrowdfundingPaymentSchedule) -> Installment:
    return (entry.due_date, Decimal(entry.expected_capital), Decimal(entry.expected_interest))


async def plan_resync(db: AsyncSession, project: CrowdfundingProject) -> ResyncPlan:
    """Compare l'échéancier ouvert et le calendrier à venir enregistrés à ceux du calcul actuel, sans rien écrire.

    Les échéances soldées sont conservées ; le projet est bloqué si son capital serait attendu deux fois.
    """
    stored = (
        (
            await db.execute(
                select(CrowdfundingPaymentSchedule)
                .where(CrowdfundingPaymentSchedule.project_id == project.id)
                .order_by(CrowdfundingPaymentSchedule.due_date)
            )
        )
        .scalars()
        .all()
    )
    settled = [entry for entry in stored if entry.is_completed]
    settled_dates = {entry.due_date for entry in settled}
    upcoming = [entry for entry in contractual_schedule(project) if entry.due_date not in settled_dates]
    expected_capital = sum((Decimal(e.expected_capital) for e in [*settled, *upcoming]), Decimal("0"))
    blocker = None
    if expected_capital > Decimal(project.invested_amount) + CENT:
        blocker = DOUBLE_CAPITAL
    elif await project_owner(db, project) is None:
        blocker = NO_OWNER
    return ResyncPlan(
        project=project,
        open_before=[_installment(entry) for entry in stored if not entry.is_completed],
        open_after=[_installment(entry) for entry in upcoming],
        events_before=await calendar.stored_events(db, project.id),
        events_after=calendar.planned_events(project),
        blocker=blocker,
    )


async def apply_resync(db: AsyncSession, plan: ResyncPlan) -> None:
    """Régénère les échéances ouvertes du projet et ses événements à venir, puis valide ; refuse un projet bloqué."""
    if plan.blocker:
        raise ValueError(plan.blocker)
    project = plan.project
    owner = await project_owner(db, project)
    await refresh_schedule(db, project)
    if project.status in calendar.SYNCED_STATUSES and project.start_date and owner is not None:
        await calendar.sync_project_events(db, owner, project)
    else:
        await calendar.clear_future_events(db, project.id)
    await db.commit()
