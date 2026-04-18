"""Crowdfunding project endpoints — CRUD + dashboard + performance."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.asset import Asset, AssetType
from app.models.crowdfunding_payment_schedule import CrowdfundingPaymentSchedule
from app.models.crowdfunding_project import CrowdfundingProject, ProjectStatus
from app.models.crowdfunding_repayment import CrowdfundingRepayment
from app.models.portfolio import Portfolio
from app.models.project_audit import ProjectAudit
from app.models.project_document import ProjectDocument
from app.models.user import User
from app.schemas.crowdfunding import (
    CrowdfundingDashboardResponse,
    CrowdfundingProjectCreate,
    CrowdfundingProjectResponse,
    CrowdfundingProjectUpdate,
    PaymentScheduleEntryResponse,
    ProjectAuditResponse,
    ProjectDocumentResponse,
    RepaymentCreate,
    RepaymentResponse,
    StressTestResponse,
)
from app.services.crowdfunding_calendar_service import crowdfunding_calendar_service
from app.services.reconciliation_service import reconciliation_service
from app.services.stress_test_service import ALLOWED_DELAY_MONTHS, stress_test_service

router = APIRouter()


# ──────────────────────── helpers ────────────────────────


def _compute_schedule_status(entry: CrowdfundingPaymentSchedule) -> str:
    """Compute display status for a schedule entry."""
    if entry.is_completed:
        return "paid"
    if entry.due_date < date.today() - timedelta(days=5):
        return "overdue"
    return "pending"


def _enrich(
    project: CrowdfundingProject,
    documents: Optional[list[ProjectDocument]] = None,
    repayments: Optional[list[CrowdfundingRepayment]] = None,
    schedule: Optional[list[CrowdfundingPaymentSchedule]] = None,
) -> CrowdfundingProjectResponse:
    """Add computed fields to a project response."""
    invested = float(project.invested_amount)
    rate = float(project.annual_rate) / 100
    months = int(project.duration_months)
    received = float(project.total_received)

    projected_total = invested * rate * months / 12
    interest_earned = max(0.0, received - invested) if project.status == ProjectStatus.COMPLETED else received

    progress = 0.0
    if project.start_date and months > 0:
        elapsed = (date.today() - project.start_date).days / 30.44
        progress = min(100.0, elapsed / months * 100)

    docs = [ProjectDocumentResponse.model_validate(d) for d in (documents or [])]
    reps = [RepaymentResponse.model_validate(r) for r in (repayments or [])]

    schedule_entries = []
    for s in schedule or []:
        entry_resp = PaymentScheduleEntryResponse.model_validate(s)
        entry_resp.status = _compute_schedule_status(s)
        schedule_entries.append(entry_resp)

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
        projected_total_interest=round(projected_total, 2),
        interest_earned=round(interest_earned, 2),
        progress_percent=round(progress, 1),
        documents=docs,
        repayments=reps,
        schedule=schedule_entries,
    )


async def _get_user_projects(db: AsyncSession, user_id: uuid.UUID) -> list[CrowdfundingProject]:
    result = await db.execute(
        select(CrowdfundingProject)
        .join(Asset, CrowdfundingProject.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
        .order_by(CrowdfundingProject.created_at.desc())
    )
    return list(result.scalars().all())


async def _get_docs_for_projects(
    db: AsyncSession,
    project_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[ProjectDocument]]:
    """Load documents for a batch of projects (without file_data)."""
    if not project_ids:
        return {}
    result = await db.execute(
        select(ProjectDocument)
        .where(ProjectDocument.project_id.in_(project_ids))
        .order_by(ProjectDocument.created_at.desc())
    )
    docs: dict[uuid.UUID, list[ProjectDocument]] = {}
    for d in result.scalars().all():
        docs.setdefault(d.project_id, []).append(d)
    return docs


async def _get_repayments_for_projects(
    db: AsyncSession,
    project_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[CrowdfundingRepayment]]:
    """Load repayments for a batch of projects."""
    if not project_ids:
        return {}
    result = await db.execute(
        select(CrowdfundingRepayment)
        .where(CrowdfundingRepayment.project_id.in_(project_ids))
        .order_by(CrowdfundingRepayment.payment_date.desc())
    )
    repayments: dict[uuid.UUID, list[CrowdfundingRepayment]] = {}
    for r in result.scalars().all():
        repayments.setdefault(r.project_id, []).append(r)
    return repayments


async def _get_schedules_for_projects(
    db: AsyncSession,
    project_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[CrowdfundingPaymentSchedule]]:
    """Load payment schedule entries for a batch of projects."""
    if not project_ids:
        return {}
    result = await db.execute(
        select(CrowdfundingPaymentSchedule)
        .where(CrowdfundingPaymentSchedule.project_id.in_(project_ids))
        .order_by(CrowdfundingPaymentSchedule.due_date)
    )
    schedules: dict[uuid.UUID, list[CrowdfundingPaymentSchedule]] = {}
    for s in result.scalars().all():
        schedules.setdefault(s.project_id, []).append(s)
    return schedules


async def _get_project_for_user(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> CrowdfundingProject:
    result = await db.execute(
        select(CrowdfundingProject)
        .join(Asset, CrowdfundingProject.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(CrowdfundingProject.id == project_id, Portfolio.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Projet non trouvé")
    return project


# ──────────────────────── CRUD ────────────────────────


@router.get("", response_model=list[CrowdfundingProjectResponse])
@limiter.limit("30/minute")
async def list_projects(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _get_user_projects(db, current_user.id)
    pids = [p.id for p in projects]
    docs_map = await _get_docs_for_projects(db, pids)
    reps_map = await _get_repayments_for_projects(db, pids)
    sched_map = await _get_schedules_for_projects(db, pids)
    return [_enrich(p, docs_map.get(p.id, []), reps_map.get(p.id, []), sched_map.get(p.id, [])) for p in projects]


@router.post("", response_model=CrowdfundingProjectResponse, status_code=201)
@limiter.limit("20/minute")
async def create_project(
    request: Request,
    data: CrowdfundingProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Resolve or auto-create a dedicated crowdfunding portfolio
    if data.portfolio_id:
        portfolio = await db.get(Portfolio, data.portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            raise HTTPException(403, "Portefeuille non trouvé")
    else:
        # Find or create a dedicated "Crowdfunding" portfolio for this user
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == current_user.id,
                Portfolio.name == "Crowdfunding",
            )
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            portfolio = Portfolio(
                id=uuid.uuid4(),
                user_id=current_user.id,
                name="Crowdfunding",
                description="Portefeuille dédié aux investissements crowdfunding",
            )
            db.add(portfolio)
            await db.flush()

    # Create the Asset row
    asset = Asset(
        id=uuid.uuid4(),
        portfolio_id=portfolio.id,
        symbol=f"{data.platform}-{data.project_name}".upper()[:20],
        name=data.project_name,
        asset_type=AssetType.CROWDFUNDING,
        quantity=Decimal("1"),
        avg_buy_price=data.invested_amount,
        current_price=data.invested_amount,
        exchange=data.platform,
        currency="EUR",
        interest_rate=data.annual_rate,
        maturity_date=data.estimated_end_date,
        project_status=data.status.value,
        invested_amount=data.invested_amount,
    )
    db.add(asset)
    await db.flush()

    # Create the CrowdfundingProject row
    project = CrowdfundingProject(
        id=uuid.uuid4(),
        asset_id=asset.id,
        platform=data.platform,
        project_name=data.project_name,
        description=data.description,
        project_url=data.project_url,
        invested_amount=data.invested_amount,
        annual_rate=data.annual_rate,
        duration_months=data.duration_months,
        repayment_type=data.repayment_type,
        interest_frequency=data.interest_frequency or "at_maturity",
        start_date=data.start_date,
        estimated_end_date=data.estimated_end_date,
        status=data.status,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Auto-generate calendar events for coupons
    await crowdfunding_calendar_service.sync_events_for_project(db, current_user.id, project)
    # Auto-generate contractual payment schedule
    await reconciliation_service.populate_initial_schedule(db, project)
    await db.commit()

    schedule = await reconciliation_service.get_schedule_for_project(db, project.id)
    return _enrich(project, schedule=schedule)


@router.get("/dashboard", response_model=CrowdfundingDashboardResponse)
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _get_user_projects(db, current_user.id)
    pids = [p.id for p in projects]
    docs_map = await _get_docs_for_projects(db, pids)
    reps_map = await _get_repayments_for_projects(db, pids)
    sched_map = await _get_schedules_for_projects(db, pids)
    enriched = [_enrich(p, docs_map.get(p.id, []), reps_map.get(p.id, []), sched_map.get(p.id, [])) for p in projects]

    total_invested = sum(float(p.invested_amount) for p in projects)
    total_received = sum(float(p.total_received) for p in projects)

    active = [p for p in projects if p.status == ProjectStatus.ACTIVE]
    projected_annual = sum(float(p.invested_amount) * float(p.annual_rate) / 100 for p in active)

    weighted_rate = 0.0
    if total_invested > 0:
        weighted_rate = sum(float(p.invested_amount) * float(p.annual_rate) for p in active) / max(
            1, sum(float(p.invested_amount) for p in active)
        )

    # Platform breakdown
    platform_map: dict[str, float] = {}
    for p in projects:
        platform_map[p.platform] = platform_map.get(p.platform, 0) + float(p.invested_amount)

    # Next maturity
    maturities = [p.estimated_end_date for p in active if p.estimated_end_date and p.estimated_end_date >= date.today()]
    next_mat = min(maturities) if maturities else None

    status_counts = {s: 0 for s in ProjectStatus}
    for p in projects:
        status_counts[p.status] += 1

    return CrowdfundingDashboardResponse(
        total_invested=round(total_invested, 2),
        total_received=round(total_received, 2),
        projected_annual_interest=round(projected_annual, 2),
        weighted_average_rate=round(weighted_rate, 3),
        active_count=status_counts[ProjectStatus.ACTIVE],
        completed_count=status_counts[ProjectStatus.COMPLETED],
        delayed_count=status_counts[ProjectStatus.DELAYED],
        defaulted_count=status_counts[ProjectStatus.DEFAULTED],
        funding_count=status_counts[ProjectStatus.FUNDING],
        next_maturity=next_mat,
        platform_breakdown=platform_map,
        projects=enriched,
    )


@router.get("/performance")
@limiter.limit("30/minute")
async def get_performance(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _get_user_projects(db, current_user.id)

    performance = []
    for p in projects:
        invested = float(p.invested_amount)
        rate = float(p.annual_rate) / 100
        months = int(p.duration_months)
        received = float(p.total_received)
        projected_total = invested * rate * months / 12

        elapsed_months = 0.0
        on_track = True
        if p.start_date:
            elapsed_months = (date.today() - p.start_date).days / 30.44
            if p.repayment_type.value == "amortizable" and elapsed_months > 0:
                expected = invested * rate * min(elapsed_months, months) / 12
                on_track = received >= expected * 0.9

        performance.append(
            {
                "id": str(p.id),
                "project_name": p.project_name,
                "platform": p.platform,
                "status": p.status.value,
                "invested_amount": invested,
                "annual_rate": float(p.annual_rate),
                "duration_months": months,
                "repayment_type": p.repayment_type.value,
                "projected_total_interest": round(projected_total, 2),
                "total_received": received,
                "interest_earned": round(
                    max(0, received - (invested if p.status == ProjectStatus.COMPLETED else 0)), 2
                ),
                "elapsed_months": round(elapsed_months, 1),
                "progress_percent": round(min(100, elapsed_months / max(1, months) * 100), 1),
                "on_track": on_track,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "estimated_end_date": p.estimated_end_date.isoformat() if p.estimated_end_date else None,
            }
        )

    return {"projects": performance}


@router.post("/sync-calendar")
@limiter.limit("5/minute")
async def sync_calendar_events(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate calendar events for all active crowdfunding projects."""
    projects = await _get_user_projects(db, current_user.id)
    total = 0
    for p in projects:
        if p.status in (ProjectStatus.ACTIVE, ProjectStatus.DELAYED):
            count = await crowdfunding_calendar_service.sync_events_for_project(db, current_user.id, p)
            total += count
    await db.commit()
    return {"synced_events": total}


# ──────────────────────── Audit Lab ────────────────────────


_MAX_FILES = 5
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/analyze", response_model=ProjectAuditResponse, status_code=201)
@limiter.limit("3/minute")
async def analyze_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    project_id: Optional[uuid.UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDFs and get an AI-powered risk analysis."""
    from app.services.ai.crowdfunding_analyzer import crowdfunding_analyzer

    if len(files) > _MAX_FILES:
        raise HTTPException(400, f"Maximum {_MAX_FILES} fichiers autorisés")

    # Validate and read files
    file_contents: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Fichier '{f.filename}' n'est pas un PDF")
        content = await f.read()
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(400, f"Fichier '{f.filename}' dépasse 10 MB")
        file_contents.append((f.filename, content))

    # Compute munitions and total capital from user's portfolios
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == current_user.id))
    portfolios = list(result.scalars().all())
    total_capital = 0.0
    munitions = 0.0
    for p in portfolios:
        assets_result = await db.execute(select(Asset).where(Asset.portfolio_id == p.id))
        for a in assets_result.scalars().all():
            val = float(a.current_price or 0) * float(a.quantity or 0)
            total_capital += val
            if a.symbol and a.symbol.upper() in {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDG"}:
                munitions += val

    try:
        audit = await crowdfunding_analyzer.analyze_documents(
            db=db,
            file_contents=file_contents,
            user_id=current_user.id,
            project_id=project_id,
            munitions=munitions,
            total_capital=total_capital,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error("Analyze error: %s", exc, exc_info=True)
        raise HTTPException(500, f"Erreur interne lors de l'analyse : {exc}") from exc
    await db.commit()
    await db.refresh(audit)
    return audit


@router.get("/audits", response_model=list[ProjectAuditResponse])
@limiter.limit("30/minute")
async def list_audits(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all audits for the current user."""
    result = await db.execute(
        select(ProjectAudit).where(ProjectAudit.user_id == current_user.id).order_by(ProjectAudit.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/audits/{audit_id}", response_model=ProjectAuditResponse)
@limiter.limit("30/minute")
async def get_audit(
    request: Request,
    audit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific audit by ID."""
    result = await db.execute(
        select(ProjectAudit).where(
            ProjectAudit.id == audit_id,
            ProjectAudit.user_id == current_user.id,
        )
    )
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(404, "Audit non trouvé")
    return audit


# ──────────────────── Payment Schedule ────────────────────


@router.get("/{project_id}/schedule", response_model=list[PaymentScheduleEntryResponse])
@limiter.limit("30/minute")
async def get_schedule(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the contractual payment schedule for a project."""
    await _get_project_for_user(db, project_id, current_user.id)
    entries = await reconciliation_service.get_schedule_for_project(db, project_id)

    result = []
    for e in entries:
        resp = PaymentScheduleEntryResponse.model_validate(e)
        resp.status = _compute_schedule_status(e)
        result.append(resp)
    return result


# ──────────────────── Repayments ────────────────────


@router.post("/{project_id}/repayments", response_model=RepaymentResponse, status_code=201)
@limiter.limit("20/minute")
async def create_repayment(
    request: Request,
    project_id: uuid.UUID,
    data: RepaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log a payment received from a crowdfunding project."""
    project = await _get_project_for_user(db, project_id, current_user.id)

    repayment = CrowdfundingRepayment(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=current_user.id,
        payment_date=data.payment_date,
        amount=data.amount,
        payment_type=data.payment_type,
        interest_amount=data.interest_amount,
        capital_amount=data.capital_amount,
        tax_amount=data.tax_amount,
        notes=data.notes,
    )
    db.add(repayment)
    await db.flush()  # Ensure repayment row exists before FK reference

    # Update cumulative total
    project.total_received = (project.total_received or Decimal("0")) + data.amount

    # Mark closest calendar event as completed
    await crowdfunding_calendar_service.mark_closest_event_completed(db, project.id, data.payment_date)

    # Reconcile with payment schedule
    await reconciliation_service.reconcile_repayment(
        db,
        project.id,
        repayment.id,
        data.payment_date,
    )

    await db.commit()
    await db.refresh(repayment)
    return repayment


@router.get("/{project_id}/repayments", response_model=list[RepaymentResponse])
@limiter.limit("30/minute")
async def list_repayments(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all repayments for a project."""
    await _get_project_for_user(db, project_id, current_user.id)
    result = await db.execute(
        select(CrowdfundingRepayment)
        .where(CrowdfundingRepayment.project_id == project_id)
        .order_by(CrowdfundingRepayment.payment_date.desc())
    )
    return list(result.scalars().all())


@router.delete("/{project_id}/repayments/{repayment_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_repayment(
    request: Request,
    project_id: uuid.UUID,
    repayment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a repayment and decrement the project total."""
    project = await _get_project_for_user(db, project_id, current_user.id)
    result = await db.execute(
        select(CrowdfundingRepayment).where(
            CrowdfundingRepayment.id == repayment_id,
            CrowdfundingRepayment.project_id == project_id,
        )
    )
    repayment = result.scalar_one_or_none()
    if not repayment:
        raise HTTPException(404, "Remboursement non trouvé")

    project.total_received = max(
        Decimal("0"),
        (project.total_received or Decimal("0")) - repayment.amount,
    )

    # Unreconcile from payment schedule before deleting
    await reconciliation_service.unreconcile_repayment(db, repayment.id)

    await db.delete(repayment)
    await db.commit()


# ──────────────────── Project Documents ────────────────────


@router.get("/documents/{doc_id}/download")
@limiter.limit("30/minute")
async def download_document(
    request: Request,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a project document PDF."""
    import io

    from fastapi.responses import StreamingResponse

    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.id == doc_id,
            ProjectDocument.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document non trouvé")

    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.file_name}"'},
    )


@router.post("/{project_id}/documents", response_model=list[ProjectDocumentResponse], status_code=201)
@limiter.limit("10/minute")
async def upload_documents(
    request: Request,
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDFs to a project and auto-trigger audit analysis."""
    from app.services.ai.crowdfunding_analyzer import crowdfunding_analyzer

    project = await _get_project_for_user(db, project_id, current_user.id)

    if len(files) > _MAX_FILES:
        raise HTTPException(400, f"Maximum {_MAX_FILES} fichiers autorisés")

    file_contents: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Fichier '{f.filename}' n'est pas un PDF")
        content = await f.read()
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(400, f"Fichier '{f.filename}' dépasse 10 MB")
        file_contents.append((f.filename, content))

    # Run audit analysis
    audit = None
    try:
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == current_user.id))
        portfolios = list(result.scalars().all())
        total_capital = 0.0
        munitions = 0.0
        for p in portfolios:
            assets_result = await db.execute(select(Asset).where(Asset.portfolio_id == p.id))
            for a in assets_result.scalars().all():
                val = float(a.current_price or 0) * float(a.quantity or 0)
                total_capital += val
                if a.asset_type in (AssetType.STABLECOIN,):
                    munitions += val

        audit = await crowdfunding_analyzer.analyze_documents(
            db=db,
            file_contents=file_contents,
            user_id=current_user.id,
            project_id=project.id,
            munitions=munitions,
            total_capital=total_capital,
        )
        await db.flush()
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Auto-audit failed for project %s", project_id, exc_info=True)

    # Store documents
    docs = []
    for fname, fdata in file_contents:
        doc = ProjectDocument(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=current_user.id,
            file_name=fname,
            file_data=fdata,
            file_size=len(fdata),
            audit_id=audit.id if audit else None,
        )
        db.add(doc)
        docs.append(doc)

    await db.commit()
    for doc in docs:
        await db.refresh(doc)

    return docs


@router.get("/{project_id}/documents", response_model=list[ProjectDocumentResponse])
@limiter.limit("30/minute")
async def list_project_documents(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for a project."""
    await _get_project_for_user(db, project_id, current_user.id)
    result = await db.execute(
        select(ProjectDocument)
        .where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.created_at.desc())
    )
    return list(result.scalars().all())


# ──────────────────── Stress Test ────────────────────


@router.get("/{project_id}/stress-test", response_model=StressTestResponse)
@limiter.limit("20/minute")
async def get_stress_test(
    request: Request,
    project_id: uuid.UUID,
    delay_months: int = Query(0, ge=0, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute degraded IRR for a project with simulated payment delays."""
    if delay_months not in ALLOWED_DELAY_MONTHS:
        raise HTTPException(400, "delay_months doit être 0, 6, 12 ou 24")

    project = await _get_project_for_user(db, project_id, current_user.id)

    try:
        result = stress_test_service.compute_stress_test(project, delay_months)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    irr_delta = None
    if result.base_irr is not None and result.stressed_irr is not None:
        irr_delta = round(result.stressed_irr - result.base_irr, 2)

    return StressTestResponse(
        project_id=project.id,
        delay_months=result.delay_months,
        base_irr=result.base_irr,
        stressed_irr=result.stressed_irr,
        irr_delta=irr_delta,
        cashflows=[
            {
                "date": cf.date,
                "capital": cf.capital,
                "interest": cf.interest,
                "total": cf.total,
                "is_delayed": cf.is_delayed,
            }
            for cf in result.cashflows
        ],
    )


# ──────────────────── Single Project CRUD ────────────────────


@router.get("/{project_id}", response_model=CrowdfundingProjectResponse)
@limiter.limit("30/minute")
async def get_project(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(db, project_id, current_user.id)
    docs_map = await _get_docs_for_projects(db, [project.id])
    reps_map = await _get_repayments_for_projects(db, [project.id])
    sched_map = await _get_schedules_for_projects(db, [project.id])
    return _enrich(project, docs_map.get(project.id, []), reps_map.get(project.id, []), sched_map.get(project.id, []))


@router.patch("/{project_id}", response_model=CrowdfundingProjectResponse)
@limiter.limit("20/minute")
async def update_project(
    request: Request,
    project_id: uuid.UUID,
    data: CrowdfundingProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(db, project_id, current_user.id)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)

    # Sync key fields back to the Asset row
    asset = await db.get(Asset, project.asset_id)
    if asset:
        if "invested_amount" in updates:
            asset.purchase_price = project.invested_amount
        if "annual_rate" in updates:
            asset.interest_rate = project.annual_rate
        if "estimated_end_date" in updates:
            asset.maturity_date = project.estimated_end_date
        if "status" in updates:
            asset.project_status = project.status.value
        if "platform" in updates:
            asset.exchange = project.platform
            asset.symbol = f"{project.platform}-{project.project_name}".upper()[:20]

    await db.commit()
    await db.refresh(project)

    # Sync calendar events and schedule if financial terms or status changed
    financial_fields = {
        "annual_rate",
        "duration_months",
        "repayment_type",
        "interest_frequency",
        "start_date",
        "estimated_end_date",
        "invested_amount",
        "tax_rate",
        "delay_months",
    }
    if updates.keys() & financial_fields:
        await crowdfunding_calendar_service.sync_events_for_project(db, current_user.id, project)
        await reconciliation_service.populate_initial_schedule(db, project)
        await db.commit()
    elif "status" in updates:
        if project.status in (ProjectStatus.COMPLETED, ProjectStatus.DEFAULTED):
            await crowdfunding_calendar_service.cleanup_completed_project(db, project.id)
            await db.commit()
        elif project.status == ProjectStatus.ACTIVE:
            await crowdfunding_calendar_service.sync_events_for_project(db, current_user.id, project)
            await reconciliation_service.populate_initial_schedule(db, project)
            await db.commit()

    schedule = await reconciliation_service.get_schedule_for_project(db, project.id)
    return _enrich(project, schedule=schedule)


@router.delete("/{project_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_project(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(db, project_id, current_user.id)

    # Delete asset (cascades to project via FK)
    asset = await db.get(Asset, project.asset_id)
    if asset:
        await db.delete(asset)
    await db.commit()
