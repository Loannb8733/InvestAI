import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from app.domains.crowdfunding.models import CrowdfundingPaymentSchedule, CrowdfundingProject, RepaymentType

MAX_SCHEDULE_MONTHS = 60
FREQUENCY_MONTHS = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}
CENT = Decimal("0.01")


def net_multiplier(project: CrowdfundingProject) -> Decimal:
    """1 - taux d'imposition ; 30 % seulement quand le taux est absent, un taux nul reste nul."""
    tax_rate = Decimal(str(project.tax_rate)) if project.tax_rate is not None else Decimal("30")
    return Decimal("1") - tax_rate / Decimal("100")


def _entry(project: CrowdfundingProject, due: date, capital: Decimal, interest: Decimal) -> CrowdfundingPaymentSchedule:
    return CrowdfundingPaymentSchedule(
        id=uuid.uuid4(),
        project_id=project.id,
        due_date=due,
        expected_capital=capital,
        expected_interest=interest,
    )


def _at_maturity(project: CrowdfundingProject, total_months: int) -> list[CrowdfundingPaymentSchedule]:
    if not project.estimated_end_date:
        return []
    invested = Decimal(str(project.invested_amount))
    rate = Decimal(str(project.annual_rate)) / Decimal("100")
    due = project.estimated_end_date + relativedelta(months=int(project.delay_months or 0))
    gross = invested * rate * Decimal(str(total_months)) / Decimal("12")
    net = (gross * net_multiplier(project)).quantize(CENT, rounding=ROUND_HALF_UP)
    return [_entry(project, due, invested, net)]


def in_fine_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier in fine : coupons nets à la fréquence choisie, capital à la fin ; le retard ajoute des périodes."""
    total_months = int(project.duration_months) + int(project.delay_months or 0)
    frequency = project.interest_frequency or "at_maturity"
    if frequency not in FREQUENCY_MONTHS:
        return _at_maturity(project, total_months)
    if not project.start_date:
        return []
    invested = Decimal(str(project.invested_amount))
    rate = Decimal(str(project.annual_rate)) / Decimal("100")
    step = FREQUENCY_MONTHS[frequency]
    coupon = invested * rate / Decimal(str(12 // step))
    coupon_net = (coupon * net_multiplier(project)).quantize(CENT, rounding=ROUND_HALF_UP)
    periods = min(total_months // step, MAX_SCHEDULE_MONTHS // step)
    return [
        _entry(
            project,
            project.start_date + relativedelta(months=step * index),
            invested if index == periods else Decimal("0"),
            coupon_net,
        )
        for index in range(1, periods + 1)
    ]


def amortizable_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier amortissable : capital constant chaque mois, la dernière échéance portant l'arrondi."""
    if not project.start_date:
        return []
    invested = Decimal(str(project.invested_amount))
    rate = Decimal(str(project.annual_rate)) / Decimal("100")
    months = min(int(project.duration_months) + int(project.delay_months or 0), MAX_SCHEDULE_MONTHS)
    interest = (invested * rate / Decimal("12") * net_multiplier(project)).quantize(CENT, rounding=ROUND_HALF_UP)
    capital = (invested / Decimal(str(months))).quantize(CENT, rounding=ROUND_HALF_UP)
    last_capital = invested - capital * Decimal(str(months - 1))
    return [
        _entry(
            project,
            project.start_date + relativedelta(months=month),
            last_capital if month == months else capital,
            interest,
        )
        for month in range(1, months + 1)
    ]


def contractual_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier contractuel du projet, non enregistré."""
    if project.repayment_type == RepaymentType.AMORTIZABLE:
        return amortizable_schedule(project)
    return in_fine_schedule(project)
