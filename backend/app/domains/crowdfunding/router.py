import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.crowdfunding import service
from app.domains.crowdfunding.audit.router import router as audit_router
from app.domains.crowdfunding.dashboard import build_dashboard
from app.domains.crowdfunding.models import CrowdfundingProject, CrowdfundingRepayment
from app.domains.crowdfunding.presenter import project_response
from app.domains.crowdfunding.reconciliation import project_schedule
from app.domains.crowdfunding.reports import cashflow_months, eligible_for_cashflow, performance_row, tax_report
from app.domains.crowdfunding.repository import (
    documents_by_project,
    project_for_user,
    repayments_by_project,
    schedules_by_project,
    user_projects,
)
from app.domains.crowdfunding.schemas import (
    CashflowMonthResponse,
    CrowdfundingDashboardResponse,
    CrowdfundingProjectCreate,
    CrowdfundingProjectResponse,
    CrowdfundingProjectUpdate,
    CrowdfundingTaxReportResponse,
    RepaymentCreate,
    RepaymentResponse,
    StressTestResponse,
)
from app.domains.crowdfunding.stress_test import ALLOWED_DELAY_MONTHS, compute_stress_test
from app.domains.identity.dependencies import CurrentUser

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


async def _responses(
    session: AsyncSession,
    projects: list[CrowdfundingProject],
    repayments: dict[uuid.UUID, list[CrowdfundingRepayment]] | None = None,
) -> list[CrowdfundingProjectResponse]:
    ids = [p.id for p in projects]
    documents = await documents_by_project(session, ids)
    if repayments is None:
        repayments = await repayments_by_project(session, ids)
    schedules = await schedules_by_project(session, ids)
    return [
        project_response(p, documents.get(p.id, []), repayments.get(p.id, []), schedules.get(p.id, []))
        for p in projects
    ]


async def _with_schedule(session: AsyncSession, project: CrowdfundingProject) -> CrowdfundingProjectResponse:
    return project_response(project, schedule=await project_schedule(session, project.id))


@router.get("", response_model=list[CrowdfundingProjectResponse])
@limiter.limit("30/minute")
async def list_projects(request: Request, user: CurrentUser, session: Session) -> list[CrowdfundingProjectResponse]:
    """Projets de l'utilisateur avec documents, versements et échéances."""
    return await _responses(session, await user_projects(session, user.id))


@router.post("", response_model=CrowdfundingProjectResponse, status_code=201)
@limiter.limit("20/minute")
async def create_project(
    request: Request, data: CrowdfundingProjectCreate, user: CurrentUser, session: Session
) -> CrowdfundingProjectResponse:
    """Crée un projet, dans le portefeuille indiqué ou dans le portefeuille crowdfunding de l'utilisateur."""
    return await _with_schedule(session, await service.create_project(session, data, user.id))


@router.get("/dashboard", response_model=CrowdfundingDashboardResponse)
@limiter.limit("30/minute")
async def get_dashboard(request: Request, user: CurrentUser, session: Session) -> CrowdfundingDashboardResponse:
    """Synthèse de la poche crowdfunding."""
    projects = await user_projects(session, user.id)
    repayments = await repayments_by_project(session, [p.id for p in projects])
    return build_dashboard(projects, repayments, await _responses(session, projects, repayments))


@router.get("/performance")
@limiter.limit("30/minute")
async def get_performance(request: Request, user: CurrentUser, session: Session) -> dict[str, list[dict[str, Any]]]:
    """Performance de chaque projet."""
    projects = await user_projects(session, user.id)
    repayments = await repayments_by_project(session, [p.id for p in projects])
    schedules = await schedules_by_project(session, [p.id for p in projects])
    return {"projects": [performance_row(p, repayments.get(p.id), schedules.get(p.id, [])) for p in projects]}


@router.get("/cashflow-schedule", response_model=list[CashflowMonthResponse])
@limiter.limit("30/minute")
async def get_cashflow_schedule(request: Request, user: CurrentUser, session: Session) -> list[CashflowMonthResponse]:
    """Échéancier consolidé des 24 prochains mois, projets en défaut exclus."""
    eligible = eligible_for_cashflow(await user_projects(session, user.id))
    return cashflow_months(eligible, await schedules_by_project(session, [p.id for p in eligible]))


@router.get("/tax-report", response_model=CrowdfundingTaxReportResponse)
@limiter.limit("30/minute")
async def get_tax_report(
    request: Request, user: CurrentUser, session: Session, year: Annotated[int | None, Query(ge=2000, le=2100)] = None
) -> CrowdfundingTaxReportResponse:
    """Rapport fiscal de l'année demandée, l'année en cours par défaut."""
    projects = await user_projects(session, user.id)
    repayments = await repayments_by_project(session, [p.id for p in projects])
    return tax_report(projects, repayments, year if year is not None else date.today().year)


@router.post("/sync-calendar")
@limiter.limit("5/minute")
async def sync_calendar_events(request: Request, user: CurrentUser, session: Session) -> dict[str, int]:
    """Régénère au calendrier les échéances des projets actifs ou en retard."""
    return {"synced_events": await service.sync_calendar(session, await user_projects(session, user.id), user.id)}


router.include_router(audit_router)


@router.post("/{project_id}/repayments", response_model=RepaymentResponse, status_code=201)
@limiter.limit("20/minute")
async def create_repayment(
    request: Request, project_id: uuid.UUID, data: RepaymentCreate, user: CurrentUser, session: Session
) -> CrowdfundingRepayment:
    """Enregistre un versement reçu."""
    return await service.add_repayment(session, project_id, data, user.id)


@router.delete("/{project_id}/repayments/{repayment_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_repayment(
    request: Request, project_id: uuid.UUID, repayment_id: uuid.UUID, user: CurrentUser, session: Session
) -> None:
    """Supprime un versement."""
    await service.remove_repayment(session, project_id, repayment_id, user.id)


@router.get("/{project_id}/stress-test", response_model=StressTestResponse)
@limiter.limit("20/minute")
async def get_stress_test(
    request: Request,
    project_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    delay_months: Annotated[int, Query(ge=0, le=24)] = 0,
) -> StressTestResponse:
    """TRI dégradé du projet si toutes ses échéances glissent de 0, 6, 12 ou 24 mois."""
    if delay_months not in ALLOWED_DELAY_MONTHS:
        raise HTTPException(400, "delay_months doit être 0, 6, 12 ou 24")
    project = await project_for_user(session, project_id, user.id)
    try:
        result = compute_stress_test(project, delay_months)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    delta = None
    if result.base_irr is not None and result.stressed_irr is not None:
        delta = round(result.stressed_irr - result.base_irr, 2)
    return StressTestResponse.model_validate(
        {
            "project_id": project.id,
            "delay_months": result.delay_months,
            "base_irr": result.base_irr,
            "stressed_irr": result.stressed_irr,
            "irr_delta": delta,
            "cashflows": [vars(cashflow) for cashflow in result.cashflows],
        }
    )


@router.get("/{project_id}", response_model=CrowdfundingProjectResponse)
@limiter.limit("30/minute")
async def get_project(
    request: Request, project_id: uuid.UUID, user: CurrentUser, session: Session
) -> CrowdfundingProjectResponse:
    """Projet de l'utilisateur avec documents, versements et échéances."""
    return (await _responses(session, [await project_for_user(session, project_id, user.id)]))[0]


@router.patch("/{project_id}", response_model=CrowdfundingProjectResponse)
@limiter.limit("20/minute")
async def update_project(
    request: Request, project_id: uuid.UUID, data: CrowdfundingProjectUpdate, user: CurrentUser, session: Session
) -> CrowdfundingProjectResponse:
    """Modifie un projet et resynchronise calendrier et échéancier quand ses conditions changent."""
    return await _with_schedule(session, await service.update_project(session, project_id, data, user.id))


@router.delete("/{project_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_project(request: Request, project_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """Supprime un projet et son actif."""
    await service.delete_project(session, project_id, user.id)
