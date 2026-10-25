from dataclasses import dataclass
from datetime import datetime

from dateutil.relativedelta import relativedelta

from app.domains.analytics.xirr import xirr
from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject
from app.domains.crowdfunding.schedule import contractual_schedule

ALLOWED_DELAY_MONTHS = frozenset({0, 6, 12, 24})


@dataclass
class StressTestCashflow:
    date: str
    capital: float
    interest: float
    total: float
    is_delayed: bool


@dataclass
class StressTestResult:
    """TRI de base et TRI dégradé, en pourcentage."""

    base_irr: float | None
    stressed_irr: float | None
    delay_months: int
    cashflows: list[StressTestCashflow]


def _xirr_flows(
    schedule: list[CrowdfundingPaymentSchedule], invested: float, invested_at: datetime, delay_months: int
) -> list[tuple[datetime, float]]:
    flows: list[tuple[datetime, float]] = [(invested_at, -invested)]
    for entry in schedule:
        payment = float(entry.expected_capital) + float(entry.expected_interest)
        if payment <= 0:
            continue
        due = datetime.combine(entry.due_date, datetime.min.time())
        if delay_months > 0:
            due += relativedelta(months=delay_months)
        flows.append((due, payment))
    return flows


def _cashflows(schedule: list[CrowdfundingPaymentSchedule], delay_months: int) -> list[StressTestCashflow]:
    cashflows = []
    for entry in schedule:
        due = entry.due_date + relativedelta(months=delay_months) if delay_months > 0 else entry.due_date
        capital = float(entry.expected_capital)
        interest = float(entry.expected_interest)
        cashflows.append(
            StressTestCashflow(
                date=due.isoformat(),
                capital=round(capital, 2),
                interest=round(interest, 2),
                total=round(capital + interest, 2),
                is_delayed=delay_months > 0,
            )
        )
    return cashflows


def _irr_percent(flows: list[tuple[datetime, float]]) -> float | None:
    rate = xirr(flows)
    return round(rate * 100, 2) if rate is not None else None


def compute_stress_test(project: CrowdfundingProject, delay_months: int) -> StressTestResult:
    """TRI de l'échéancier contractuel, puis avec toutes les échéances décalées de ``delay_months`` mois.

    ``ValueError`` quand l'échéancier est vide ou que le projet n'a pas de date de début.
    """
    schedule = contractual_schedule(project)
    if not schedule:
        raise ValueError(
            "Impossible de calculer le stress test : échéancier vide (vérifiez la date de début et la durée du projet)."
        )
    if not project.start_date:
        raise ValueError("Le projet n'a pas de date de début.")
    invested = float(project.invested_amount)
    invested_at = datetime.combine(project.start_date, datetime.min.time())
    base_irr = _irr_percent(_xirr_flows(schedule, invested, invested_at, 0))
    if delay_months == 0:
        stressed_irr = base_irr
    else:
        stressed_irr = _irr_percent(_xirr_flows(schedule, invested, invested_at, delay_months))
    return StressTestResult(
        base_irr=base_irr,
        stressed_irr=stressed_irr,
        delay_months=delay_months,
        cashflows=_cashflows(schedule, delay_months),
    )
