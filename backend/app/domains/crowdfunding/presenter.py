from datetime import date

from app.domains.crowdfunding.models import (
    CrowdfundingPaymentSchedule,
    CrowdfundingProject,
    CrowdfundingRepayment,
    ProjectDocument,
)
from app.domains.crowdfunding.returns import interest_earned, projected_interest, schedule_status
from app.domains.crowdfunding.schemas import (
    CrowdfundingProjectResponse,
    PaymentScheduleEntryResponse,
    ProjectDocumentResponse,
    RepaymentResponse,
)

DAYS_PER_MONTH = 30.44


def _progress(project: CrowdfundingProject) -> float:
    months = int(project.duration_months)
    if not project.start_date or months <= 0:
        return 0.0
    elapsed = max(0.0, (date.today() - project.start_date).days / DAYS_PER_MONTH)
    return min(100.0, elapsed / months * 100)


def _schedule(entries: list[CrowdfundingPaymentSchedule]) -> list[PaymentScheduleEntryResponse]:
    responses = []
    for entry in entries:
        response = PaymentScheduleEntryResponse.model_validate(entry)
        response.status = schedule_status(entry)
        responses.append(response)
    return responses


def project_response(
    project: CrowdfundingProject,
    documents: list[ProjectDocument] | None = None,
    repayments: list[CrowdfundingRepayment] | None = None,
    schedule: list[CrowdfundingPaymentSchedule] | None = None,
) -> CrowdfundingProjectResponse:
    """Projet enrichi de ses intérêts projetés et perçus, de son avancement, de ses documents et échéances."""
    gross, net = projected_interest(project)
    return CrowdfundingProjectResponse(
        id=project.id,
        asset_id=project.asset_id,
        platform=project.platform,
        project_name=project.project_name,
        description=project.description,
        project_url=project.project_url,
        invested_amount=project.invested_amount,
        annual_rate=project.annual_rate,
        duration_months=int(project.duration_months),
        repayment_type=project.repayment_type,
        interest_frequency=project.interest_frequency or "at_maturity",
        tax_rate=project.tax_rate,
        delay_months=int(project.delay_months or 0),
        start_date=project.start_date,
        estimated_end_date=project.estimated_end_date,
        actual_end_date=project.actual_end_date,
        status=project.status,
        total_received=project.total_received,
        created_at=project.created_at,
        updated_at=project.updated_at,
        projected_total_interest=round(net, 2),
        projected_interest_gross=round(gross, 2),
        interest_earned=round(interest_earned(project, repayments), 2),
        progress_percent=round(_progress(project), 1),
        documents=[ProjectDocumentResponse.model_validate(document) for document in documents or []],
        repayments=[RepaymentResponse.model_validate(repayment) for repayment in repayments or []],
        schedule=_schedule(schedule or []),
    )
