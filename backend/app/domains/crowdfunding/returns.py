from datetime import date, datetime, timedelta
from decimal import Decimal

from app.domains.analytics.xirr import xirr
from app.domains.crowdfunding.models import (
    CrowdfundingPaymentSchedule,
    CrowdfundingProject,
    CrowdfundingRepayment,
    PaymentType,
    ProjectStatus,
)

XIRR_MIN_SPAN_DAYS = 30
OVERDUE_GRACE_DAYS = 5


def compute_xirr(flows: list[tuple[date, float]]) -> float | None:
    """Taux annualisé (décimal) qui annule la valeur actuelle de flux datés ; négatif = sortie, positif = entrée.

    ``None`` sans sortie ni entrée, sur moins de 30 jours, ou sans convergence du solveur partagé.
    """
    if len(flows) < 2:
        return None
    if not (any(amount < 0 for _, amount in flows) and any(amount > 0 for _, amount in flows)):
        return None
    dates = [day for day, _ in flows]
    if (max(dates) - min(dates)).days < XIRR_MIN_SPAN_DAYS:
        return None
    return xirr([(datetime(day.year, day.month, day.day), amount) for day, amount in flows])


def split_repayment(repayment: CrowdfundingRepayment) -> tuple[float, float]:
    """(intérêts, capital) d'un versement : la répartition saisie, sinon tout en intérêt (INTEREST) ou en capital."""
    amount = float(repayment.amount or 0)
    interest = float(repayment.interest_amount or 0)
    capital = float(repayment.capital_amount or 0)
    if interest == 0 and capital == 0:
        if repayment.payment_type == PaymentType.INTEREST:
            return amount, 0.0
        return 0.0, amount
    return interest, capital


def realized_xirr(project: CrowdfundingProject, repayments: list[CrowdfundingRepayment] | None = None) -> float | None:
    """XIRR réalisé : l'investissement, les versements hors parrainage, et le capital restant dû à ce jour.

    Le capital restant dû vaut zéro pour un projet en défaut.
    """
    if not project.start_date:
        return None
    invested = float(project.invested_amount or 0)
    if invested <= 0:
        return None
    flows: list[tuple[date, float]] = [(project.start_date, -invested)]
    capital_repaid = 0.0
    for repayment in repayments or []:
        if repayment.payment_type == PaymentType.REFERRAL:
            continue
        amount = float(repayment.amount or 0)
        if amount > 0:
            flows.append((repayment.payment_date, amount))
        capital_repaid += split_repayment(repayment)[1]
    if project.status != ProjectStatus.DEFAULTED:
        outstanding = max(0.0, invested - capital_repaid)
        if outstanding > 0:
            flows.append((date.today(), outstanding))
    return compute_xirr(flows)


def schedule_status(entry: CrowdfundingPaymentSchedule) -> str:
    """« paid », « overdue » passé 5 jours de grâce, sinon « pending »."""
    if entry.is_completed:
        return "paid"
    if entry.due_date < date.today() - timedelta(days=OVERDUE_GRACE_DAYS):
        return "overdue"
    return "pending"


def interest_earned(project: CrowdfundingProject, repayments: list[CrowdfundingRepayment] | None = None) -> float:
    """Intérêts perçus : le reçu au-delà de l'investi pour un projet terminé, sinon la somme des intérêts saisis."""
    if project.status == ProjectStatus.COMPLETED:
        return max(0.0, float(project.total_received or 0) - float(project.invested_amount or 0))
    if not repayments:
        return 0.0
    return float(sum((repayment.interest_amount or Decimal("0")) for repayment in repayments))


def projected_interest(project: CrowdfundingProject) -> tuple[float, float]:
    """(brut, net d'impôt) des intérêts contractuels sur toute la durée."""
    rate = float(project.annual_rate) / 100
    gross = float(project.invested_amount) * rate * int(project.duration_months) / 12
    return gross, gross * (1 - float(project.tax_rate or 0) / 100)
