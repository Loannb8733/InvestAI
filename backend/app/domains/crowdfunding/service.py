import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.crowdfunding import calendar
from app.domains.crowdfunding.models import CrowdfundingProject, CrowdfundingRepayment, PaymentType, ProjectStatus
from app.domains.crowdfunding.reconciliation import (
    reconcile_repayment,
    refresh_schedule,
    unreconcile_repayment,
)
from app.domains.crowdfunding.repository import project_for_user, resolve_crowdfunding_portfolio
from app.domains.crowdfunding.schemas import CrowdfundingProjectCreate, CrowdfundingProjectUpdate, RepaymentCreate
from app.domains.portfolio.models import Asset, AssetType, Portfolio

PATCHABLE = frozenset(
    {
        "project_name",
        "description",
        "project_url",
        "platform",
        "invested_amount",
        "annual_rate",
        "duration_months",
        "repayment_type",
        "start_date",
        "estimated_end_date",
        "actual_end_date",
        "status",
        "interest_frequency",
        "tax_rate",
        "delay_months",
        "total_received",
    }
)
FINANCIAL_FIELDS = frozenset(
    {
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
)
CLOSED_STATUSES = (ProjectStatus.COMPLETED, ProjectStatus.DEFAULTED)


def _symbol(platform: str, project_name: str | None) -> str:
    return f"{platform}-{project_name}".upper()[:20]


async def _target_portfolio(db: AsyncSession, data: CrowdfundingProjectCreate, user_id: uuid.UUID) -> Portfolio:
    if not data.portfolio_id:
        return await resolve_crowdfunding_portfolio(db, user_id)
    portfolio = await db.get(Portfolio, data.portfolio_id)
    if not portfolio or portfolio.user_id != user_id:
        raise HTTPException(404, "Portefeuille non trouvé")
    return portfolio


async def create_project(db: AsyncSession, data: CrowdfundingProjectCreate, user_id: uuid.UUID) -> CrowdfundingProject:
    """Crée l'actif et le projet, puis ses échéances au calendrier et son échéancier contractuel."""
    portfolio = await _target_portfolio(db, data, user_id)
    asset = Asset(
        id=uuid.uuid4(),
        portfolio_id=portfolio.id,
        symbol=_symbol(data.platform, data.project_name),
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
        tax_rate=data.tax_rate,
        delay_months=data.delay_months,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    await calendar.sync_project_events(db, user_id, project)
    await refresh_schedule(db, project)
    await db.commit()
    return project


def _sync_asset(asset: Asset, project: CrowdfundingProject, updated: set[str]) -> None:
    if "invested_amount" in updated:
        asset.invested_amount = project.invested_amount
        asset.avg_buy_price = project.invested_amount
        asset.current_price = project.invested_amount
    if "project_name" in updated:
        asset.name = project.project_name
    if "annual_rate" in updated:
        asset.interest_rate = project.annual_rate
    if "estimated_end_date" in updated:
        asset.maturity_date = project.estimated_end_date
    if "status" in updated:
        asset.project_status = project.status.value
    if "platform" in updated:
        asset.exchange = project.platform
    if updated & {"platform", "project_name"}:
        asset.symbol = _symbol(project.platform, project.project_name)


async def _resync_after_update(
    db: AsyncSession, user_id: uuid.UUID, project: CrowdfundingProject, updated: set[str]
) -> None:
    if updated & FINANCIAL_FIELDS or ("status" in updated and project.status == ProjectStatus.ACTIVE):
        await calendar.sync_project_events(db, user_id, project)
        await refresh_schedule(db, project)
        await db.commit()
    elif "status" in updated and project.status in CLOSED_STATUSES:
        await calendar.clear_future_events(db, project.id)
        await db.commit()


async def update_project(
    db: AsyncSession, project_id: uuid.UUID, data: CrowdfundingProjectUpdate, user_id: uuid.UUID
) -> CrowdfundingProject:
    """Applique les champs fournis, les reporte sur l'actif, puis resynchronise calendrier et échéancier."""
    project = await project_for_user(db, project_id, user_id)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field in PATCHABLE:
            setattr(project, field, value)
    asset = await db.get(Asset, project.asset_id)
    if asset:
        _sync_asset(asset, project, set(updates))
    await db.commit()
    await db.refresh(project)
    await _resync_after_update(db, user_id, project, set(updates))
    return project


async def add_repayment(
    db: AsyncSession, project_id: uuid.UUID, data: RepaymentCreate, user_id: uuid.UUID
) -> CrowdfundingRepayment:
    """Enregistre un versement au total reçu et, sauf parrainage, le rapproche du calendrier et de l'échéancier."""
    project = await project_for_user(db, project_id, user_id)
    repayment = CrowdfundingRepayment(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user_id,
        payment_date=data.payment_date,
        amount=data.amount,
        payment_type=data.payment_type,
        interest_amount=data.interest_amount,
        capital_amount=data.capital_amount,
        tax_amount=data.tax_amount,
        notes=data.notes,
    )
    db.add(repayment)
    await db.flush()
    project.total_received = (project.total_received or Decimal("0")) + data.amount
    if data.payment_type != PaymentType.REFERRAL:
        await calendar.complete_closest_event(db, project.id, data.payment_date)
        await reconcile_repayment(db, project.id, repayment.id, data.payment_date, amount=data.amount)
    await db.commit()
    await db.refresh(repayment)
    return repayment


async def remove_repayment(
    db: AsyncSession, project_id: uuid.UUID, repayment_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Supprime un versement, le retire du total reçu et rouvre l'échéance qu'il soldait."""
    project = await project_for_user(db, project_id, user_id)
    result = await db.execute(
        select(CrowdfundingRepayment).where(
            CrowdfundingRepayment.id == repayment_id,
            CrowdfundingRepayment.project_id == project_id,
        )
    )
    repayment = result.scalar_one_or_none()
    if not repayment:
        raise HTTPException(404, "Remboursement non trouvé")
    project.total_received = max(Decimal("0"), (project.total_received or Decimal("0")) - repayment.amount)
    await unreconcile_repayment(db, repayment.id)
    await db.delete(repayment)
    await db.commit()


async def delete_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Supprime l'actif du projet, et le projet avec lui."""
    project = await project_for_user(db, project_id, user_id)
    asset = await db.get(Asset, project.asset_id)
    if asset:
        await db.delete(asset)
    await db.commit()


async def sync_calendar(db: AsyncSession, projects: list[CrowdfundingProject], user_id: uuid.UUID) -> int:
    """Régénère au calendrier les échéances des projets actifs ou en retard ; rend le nombre d'événements."""
    total = 0
    for project in projects:
        if project.status in calendar.SYNCED_STATUSES:
            total += await calendar.sync_project_events(db, user_id, project)
    await db.commit()
    return total
