import uuid
from datetime import date
from typing import Any

from app.domains.crowdfunding.models import (
    CrowdfundingPaymentSchedule,
    CrowdfundingProject,
    CrowdfundingRepayment,
    PaymentType,
    ProjectStatus,
    RepaymentType,
)
from app.domains.crowdfunding.presenter import DAYS_PER_MONTH
from app.domains.crowdfunding.returns import (
    interest_earned,
    projected_interest,
    realized_xirr,
    schedule_status,
    split_repayment,
)
from app.domains.crowdfunding.schemas import (
    CashflowMonthResponse,
    CashflowProjectAmount,
    CrowdfundingTaxReportResponse,
    TaxReportPlatform,
)

CASHFLOW_MONTHS = 24
FLAT_TAX = 0.30
WITHHOLDING_TOLERANCE = 1.0
ON_TRACK_RATIO = 0.9


def _on_track(project: CrowdfundingProject, schedule: list[CrowdfundingPaymentSchedule], elapsed: float) -> bool:
    if schedule:
        return all(schedule_status(entry) != "overdue" for entry in schedule)
    if not (project.start_date and project.repayment_type == RepaymentType.AMORTIZABLE and elapsed > 0):
        return True
    months = int(project.duration_months)
    expected = float(project.invested_amount) * (float(project.annual_rate) / 100) * min(elapsed, months) / 12
    return float(project.total_received) >= expected * ON_TRACK_RATIO


def performance_row(
    project: CrowdfundingProject,
    repayments: list[CrowdfundingRepayment] | None,
    schedule: list[CrowdfundingPaymentSchedule],
) -> dict[str, Any]:
    """Performance d'un projet : XIRR réalisé et écart au taux contractuel, avancement, échéances respectées."""
    months = int(project.duration_months)
    gross, net = projected_interest(project)
    elapsed = (date.today() - project.start_date).days / DAYS_PER_MONTH if project.start_date else 0.0
    rate = realized_xirr(project, repayments)
    realized = round(rate * 100, 2) if rate is not None else None
    return {
        "id": str(project.id),
        "project_name": project.project_name,
        "platform": project.platform,
        "status": project.status.value,
        "invested_amount": float(project.invested_amount),
        "annual_rate": float(project.annual_rate),
        "duration_months": months,
        "repayment_type": project.repayment_type.value,
        "projected_total_interest": round(net, 2),
        "projected_interest_gross": round(gross, 2),
        "total_received": float(project.total_received),
        "interest_earned": round(interest_earned(project, repayments), 2),
        "realized_xirr": realized,
        "xirr_gap": round(realized - float(project.annual_rate), 2) if realized is not None else None,
        "elapsed_months": round(elapsed, 1),
        "progress_percent": round(min(100, elapsed / max(1, months) * 100), 1),
        "on_track": _on_track(project, schedule, elapsed),
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "estimated_end_date": project.estimated_end_date.isoformat() if project.estimated_end_date else None,
    }


def _window(today: date) -> tuple[date, date]:
    end_index = today.year * 12 + (today.month - 1) + CASHFLOW_MONTHS
    return today.replace(day=1), date(end_index // 12, end_index % 12 + 1, 1)


def cashflow_months(
    projects: list[CrowdfundingProject], schedules: dict[uuid.UUID, list[CrowdfundingPaymentSchedule]]
) -> list[CashflowMonthResponse]:
    """Échéances non soldées des 24 prochains mois, mois courant inclus, par mois ; les mois vides sont omis."""
    names = {p.id: (p.project_name or p.platform) for p in projects}
    start, end = _window(date.today())
    buckets: dict[str, dict[str, Any]] = {}
    for project_id, entries in schedules.items():
        for entry in entries:
            if entry.is_completed or not (start <= entry.due_date < end):
                continue
            key = f"{entry.due_date.year:04d}-{entry.due_date.month:02d}"
            bucket = buckets.setdefault(key, {"capital": 0.0, "interest": 0.0, "projects": {}})
            capital = float(entry.expected_capital or 0)
            interest = float(entry.expected_interest or 0)
            bucket["capital"] += capital
            bucket["interest"] += interest
            name = names.get(project_id, "Projet")
            bucket["projects"][name] = bucket["projects"].get(name, 0.0) + capital + interest
    return [
        CashflowMonthResponse(
            month=key,
            expected_capital=round(bucket["capital"], 2),
            expected_interest=round(bucket["interest"], 2),
            total=round(bucket["capital"] + bucket["interest"], 2),
            projects=[
                CashflowProjectAmount(name=name, amount=round(amount, 2))
                for name, amount in sorted(bucket["projects"].items(), key=lambda kv: -kv[1])
            ],
        )
        for key, bucket in sorted(buckets.items())
    ]


def _platform_totals(
    projects: list[CrowdfundingProject], repayments: dict[uuid.UUID, list[CrowdfundingRepayment]], year: int
) -> dict[str, dict[str, float]]:
    platforms = {p.id: p.platform for p in projects}
    buckets: dict[str, dict[str, float]] = {}
    for project_id, rows in repayments.items():
        for repayment in rows:
            if repayment.payment_date.year != year or repayment.payment_type == PaymentType.REFERRAL:
                continue
            bucket = buckets.setdefault(platforms.get(project_id, "Inconnue"), {"gross": 0.0, "tax": 0.0, "count": 0.0})
            bucket["gross"] += split_repayment(repayment)[0]
            bucket["tax"] += float(repayment.tax_amount or 0)
            bucket["count"] += 1
    return buckets


def tax_report(
    projects: list[CrowdfundingProject], repayments: dict[uuid.UUID, list[CrowdfundingRepayment]], year: int
) -> CrowdfundingTaxReportResponse:
    """Intérêts bruts, retenues et net par plateforme sur l'année, face au PFU de 30 %, pour rapprocher les IFU."""
    buckets = _platform_totals(projects, repayments, year)
    platforms = []
    for name in sorted(buckets, key=str.casefold):
        gross, tax = buckets[name]["gross"], buckets[name]["tax"]
        pfu = gross * FLAT_TAX
        platforms.append(
            TaxReportPlatform(
                platform=name,
                gross_interest=round(gross, 2),
                tax_withheld=round(tax, 2),
                net_interest=round(gross - tax, 2),
                theoretical_pfu=round(pfu, 2),
                withholding_gap=abs(tax - pfu) > WITHHOLDING_TOLERANCE,
                nb_payments=int(buckets[name]["count"]),
            )
        )
    return CrowdfundingTaxReportResponse(
        year=year,
        platforms=platforms,
        total_gross_interest=round(sum(p.gross_interest for p in platforms), 2),
        total_tax_withheld=round(sum(p.tax_withheld for p in platforms), 2),
        total_net_interest=round(sum(p.net_interest for p in platforms), 2),
        total_theoretical_pfu=round(sum(p.theoretical_pfu for p in platforms), 2),
        nb_payments=sum(p.nb_payments for p in platforms),
    )


def eligible_for_cashflow(projects: list[CrowdfundingProject]) -> list[CrowdfundingProject]:
    """Projets hors défaut."""
    return [p for p in projects if p.status != ProjectStatus.DEFAULTED]
