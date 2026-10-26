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


def _coupons(start: date, step: int, horizon: int, coupon_net: Decimal) -> list[tuple[date, Decimal]]:
    dates = [(start + relativedelta(months=month), coupon_net) for month in range(step, horizon + 1, step)]
    remainder = horizon % step
    if remainder:
        partial = (coupon_net * Decimal(remainder) / Decimal(step)).quantize(CENT, rounding=ROUND_HALF_UP)
        dates.append((start + relativedelta(months=horizon), partial))
    return dates


def in_fine_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier in fine : coupons nets à la fréquence choisie, capital à la fin ; le retard ajoute des périodes.

    Une dernière période incomplète porte le capital et un coupon au prorata de ses mois.
    """
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
    coupons = _coupons(project.start_date, step, min(total_months, MAX_SCHEDULE_MONTHS), coupon_net)
    last = len(coupons) - 1
    return [
        _entry(project, due, invested if index == last else Decimal("0"), interest)
        for index, (due, interest) in enumerate(coupons)
    ]


def amortizable_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier amortissable : capital constant chaque mois, intérêts nets sur le capital restant dû.

    La dernière échéance porte l'arrondi du capital.
    """
    if not project.start_date:
        return []
    invested = Decimal(str(project.invested_amount))
    monthly_rate = Decimal(str(project.annual_rate)) / Decimal("100") / Decimal("12") * net_multiplier(project)
    months = min(int(project.duration_months) + int(project.delay_months or 0), MAX_SCHEDULE_MONTHS)
    capital = (invested / Decimal(str(months))).quantize(CENT, rounding=ROUND_HALF_UP)
    entries = []
    for month in range(1, months + 1):
        outstanding = invested - capital * Decimal(month - 1)
        interest = (outstanding * monthly_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        repaid = outstanding if month == months else capital
        entries.append(_entry(project, project.start_date + relativedelta(months=month), repaid, interest))
    return entries


def contractual_schedule(project: CrowdfundingProject) -> list[CrowdfundingPaymentSchedule]:
    """Échéancier contractuel du projet, non enregistré."""
    if project.repayment_type == RepaymentType.AMORTIZABLE:
        return amortizable_schedule(project)
    return in_fine_schedule(project)
