import uuid
from dataclasses import dataclass, field
from datetime import date

from app.domains.crowdfunding.models import CrowdfundingProject, CrowdfundingRepayment, PaymentType, ProjectStatus
from app.domains.crowdfunding.returns import split_repayment
from app.domains.crowdfunding.schemas import CrowdfundingDashboardResponse, CrowdfundingProjectResponse

RATED_STATUSES = frozenset({ProjectStatus.ACTIVE, ProjectStatus.DELAYED, ProjectStatus.COMPLETED})


@dataclass
class _Receipts:
    interest: float = 0.0
    interest_net: float = 0.0
    referral: float = 0.0
    capital_by_project: dict[uuid.UUID, float] = field(default_factory=dict)


def _receipts(repayments: dict[uuid.UUID, list[CrowdfundingRepayment]]) -> _Receipts:
    receipts = _Receipts()
    for project_id, rows in repayments.items():
        capital_total = 0.0
        for repayment in rows:
            if repayment.payment_type == PaymentType.REFERRAL:
                receipts.referral += float(repayment.amount or 0)
                continue
            interest, capital = split_repayment(repayment)
            receipts.interest += interest
            receipts.interest_net += max(0.0, float(repayment.amount or 0) - capital)
            capital_total += capital
        receipts.capital_by_project[project_id] = capital_total
    return receipts


def _outstanding(projects: list[CrowdfundingProject], capital: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    return {p.id: max(0.0, float(p.invested_amount) - capital.get(p.id, 0.0)) for p in projects}


def _platform_outstanding(projects: list[CrowdfundingProject], outstanding: dict[uuid.UUID, float]) -> dict[str, float]:
    by_platform: dict[str, float] = {}
    for project in projects:
        if project.status == ProjectStatus.DEFAULTED or outstanding[project.id] <= 0:
            continue
        by_platform[project.platform] = by_platform.get(project.platform, 0.0) + outstanding[project.id]
    return {platform: round(amount, 2) for platform, amount in by_platform.items()}


def _weighted_rate(projects: list[CrowdfundingProject]) -> float:
    rated = [p for p in projects if p.status in RATED_STATUSES]
    invested = sum(float(p.invested_amount) for p in rated)
    if invested <= 0:
        return 0.0
    return sum(float(p.invested_amount) * float(p.annual_rate) for p in rated) / invested


def _next_maturity(active: list[CrowdfundingProject]) -> date | None:
    maturities = [p.estimated_end_date for p in active if p.estimated_end_date and p.estimated_end_date >= date.today()]
    return min(maturities) if maturities else None


def build_dashboard(
    projects: list[CrowdfundingProject],
    repayments: dict[uuid.UUID, list[CrowdfundingRepayment]],
    responses: list[CrowdfundingProjectResponse],
) -> CrowdfundingDashboardResponse:
    """Synthèse de la poche : un versement sans répartition saisie compte en capital, sauf s'il est déclaré intérêt."""
    receipts = _receipts(repayments)
    outstanding = _outstanding(projects, receipts.capital_by_project)
    defaulted = {p.id for p in projects if p.status == ProjectStatus.DEFAULTED}
    active = [p for p in projects if p.status == ProjectStatus.ACTIVE]
    platform_map: dict[str, float] = {}
    for project in projects:
        platform_map[project.platform] = platform_map.get(project.platform, 0) + float(project.invested_amount)
    counts = {status: 0 for status in ProjectStatus}
    for project in projects:
        counts[project.status] += 1
    return CrowdfundingDashboardResponse(
        total_invested=round(sum(float(p.invested_amount) for p in projects), 2),
        total_received=round(sum(float(p.total_received) for p in projects), 2),
        total_interest_received=round(receipts.interest, 2),
        total_interest_net=round(receipts.interest_net, 2),
        total_capital_repaid=round(sum(receipts.capital_by_project.values()), 2),
        total_referral=round(receipts.referral, 2),
        capital_outstanding=round(sum(v for k, v in outstanding.items() if k not in defaulted), 2),
        defaulted_outstanding=round(sum(v for k, v in outstanding.items() if k in defaulted), 2),
        projected_annual_interest=round(sum(float(p.invested_amount) * float(p.annual_rate) / 100 for p in active), 2),
        weighted_average_rate=round(_weighted_rate(projects), 3),
        active_count=counts[ProjectStatus.ACTIVE],
        completed_count=counts[ProjectStatus.COMPLETED],
        delayed_count=counts[ProjectStatus.DELAYED],
        defaulted_count=counts[ProjectStatus.DEFAULTED],
        funding_count=counts[ProjectStatus.FUNDING],
        next_maturity=_next_maturity(active),
        platform_breakdown=platform_map,
        platform_breakdown_outstanding=_platform_outstanding(projects, outstanding),
        projects=responses,
    )
