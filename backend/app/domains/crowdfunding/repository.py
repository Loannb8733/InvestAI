import uuid
from collections.abc import Sequence
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.domains.crowdfunding.models import (
    CrowdfundingPaymentSchedule,
    CrowdfundingProject,
    CrowdfundingRepayment,
    ProjectDocument,
)
from app.domains.portfolio.models import CROWDFUNDING_KIND, Asset, Portfolio

PROJECT_NOT_FOUND = "Projet non trouvé"


class _ByProject(Protocol):
    project_id: uuid.UUID


async def resolve_crowdfunding_portfolio(db: AsyncSession, user_id: uuid.UUID) -> Portfolio:
    """Portefeuille géré par l'application pour le crowdfunding, retrouvé par son marqueur et créé au besoin.

    Le repli sur le nom « Crowdfunding » rattrape les portefeuilles créés avant le marqueur et les marque.
    """
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_id,
            or_(Portfolio.kind == CROWDFUNDING_KIND, Portfolio.name == "Crowdfunding"),
        )
    )
    portfolio = result.scalars().first()
    if portfolio is not None:
        if portfolio.kind != CROWDFUNDING_KIND:
            portfolio.kind = CROWDFUNDING_KIND
        return portfolio
    portfolio = Portfolio(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Crowdfunding",
        kind=CROWDFUNDING_KIND,
        description="Portefeuille dédié aux investissements crowdfunding",
    )
    db.add(portfolio)
    await db.flush()
    return portfolio


def _owned(query: Select[CrowdfundingProject], user_id: uuid.UUID) -> Select[CrowdfundingProject]:
    return (
        query.join(Asset, CrowdfundingProject.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
    )


async def project_owner(db: AsyncSession, project: CrowdfundingProject) -> uuid.UUID | None:
    """Propriétaire du projet, par son actif et son portefeuille ; None si l'un manque."""
    asset = await db.get(Asset, project.asset_id)
    if not asset:
        return None
    portfolio = await db.get(Portfolio, asset.portfolio_id)
    return portfolio.user_id if portfolio else None


async def user_projects(db: AsyncSession, user_id: uuid.UUID) -> list[CrowdfundingProject]:
    """Projets de l'utilisateur, du plus récent au plus ancien."""
    query = _owned(select(CrowdfundingProject), user_id).order_by(CrowdfundingProject.created_at.desc())
    return list((await db.execute(query)).scalars().all())


async def project_for_user(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> CrowdfundingProject:
    """Projet de l'utilisateur, ou 404."""
    query = _owned(select(CrowdfundingProject), user_id).where(CrowdfundingProject.id == project_id)
    project = (await db.execute(query)).scalar_one_or_none()
    if not project:
        raise HTTPException(404, PROJECT_NOT_FOUND)
    return project


def _group[T: _ByProject](rows: Sequence[T]) -> dict[uuid.UUID, list[T]]:
    grouped: dict[uuid.UUID, list[T]] = {}
    for row in rows:
        grouped.setdefault(row.project_id, []).append(row)
    return grouped


async def documents_by_project(
    db: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ProjectDocument]]:
    """Documents des projets, sans leur contenu binaire, du plus récent au plus ancien."""
    if not project_ids:
        return {}
    query = (
        select(ProjectDocument)
        .options(defer(ProjectDocument.file_data))
        .where(ProjectDocument.project_id.in_(project_ids))
        .order_by(ProjectDocument.created_at.desc())
    )
    return _group((await db.execute(query)).scalars().all())


async def repayments_by_project(
    db: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[CrowdfundingRepayment]]:
    """Versements des projets, du plus récent au plus ancien."""
    if not project_ids:
        return {}
    query = (
        select(CrowdfundingRepayment)
        .where(CrowdfundingRepayment.project_id.in_(project_ids))
        .order_by(CrowdfundingRepayment.payment_date.desc())
    )
    return _group((await db.execute(query)).scalars().all())


async def schedules_by_project(
    db: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[CrowdfundingPaymentSchedule]]:
    """Échéanciers des projets, par date d'échéance."""
    if not project_ids:
        return {}
    query = (
        select(CrowdfundingPaymentSchedule)
        .where(CrowdfundingPaymentSchedule.project_id.in_(project_ids))
        .order_by(CrowdfundingPaymentSchedule.due_date)
    )
    return _group((await db.execute(query)).scalars().all())
