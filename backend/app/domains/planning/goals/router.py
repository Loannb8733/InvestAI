import logging
from datetime import date
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User
from app.domains.planning.goals.models import Goal, GoalStatus, GoalStrategy, GoalType
from app.domains.planning.goals.projection import goal_projection_service
from app.domains.planning.goals.repository import find_owned_goal, list_user_goals
from app.domains.planning.goals.schemas import (
    GoalCreate,
    GoalProjectionResponse,
    GoalResponse,
    GoalUpdate,
    ProjectionPointResponse,
)
from app.domains.planning.goals.sync import initial_sync, sync_goals_for_user
from app.domains.portfolio.classification import is_cash_like
from app.services.crowdfunding_calendar_service import crowdfunding_calendar_service

logger = logging.getLogger(__name__)

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

GOAL_NOT_FOUND = "Objectif non trouvé"

_PATCHABLE_FIELDS = {
    "name",
    "goal_type",
    "target_amount",
    "current_amount",
    "currency",
    "target_date",
    "deadline_date",
    "priority",
    "strategy_type",
    "status",
    "icon",
    "color",
    "notes",
}


def _effective_date(goal: Goal) -> date | None:
    if goal.deadline_date:
        return goal.deadline_date
    if goal.target_date:
        try:
            return date.fromisoformat(goal.target_date)
        except ValueError:
            pass
    return None


def _monthly_needed(remaining_amount: float, effective_date: date, today: date) -> float:
    gap = relativedelta(effective_date, today)
    months_left: int = max(gap.years * 12 + gap.months, 1)
    return min(round(remaining_amount / months_left, 2), 9_999_999.99)


def _lower(value: StrEnum | None, default: str) -> str:
    return value.value.lower() if value else default


def _build_response(goal: Goal) -> dict[str, Any]:
    """Effort mensuel en mois calendaires jusqu'à ``deadline_date`` (sinon ``target_date`` ISO), plancher à un mois
    et plafond à 9 999 999,99 : même convention que la projection (FIN-07)."""
    progress = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
    progress = min(progress, 100.0)

    days_remaining = None
    monthly_needed = None
    effective_date = _effective_date(goal)
    if effective_date:
        today = date.today()
        days_remaining = max((effective_date - today).days, 0)
        remaining_amount = float(goal.target_amount - goal.current_amount)
        if remaining_amount > 0 and days_remaining > 0:
            monthly_needed = _monthly_needed(remaining_amount, effective_date, today)

    return {
        "id": goal.id,
        "goal_type": _lower(goal.goal_type, "asset"),
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "currency": goal.currency,
        "target_date": goal.target_date,
        "deadline_date": str(goal.deadline_date) if goal.deadline_date else None,
        "priority": _lower(goal.priority, "medium"),
        "strategy_type": _lower(goal.strategy_type, "moderate"),
        "status": _lower(goal.status, "active"),
        "icon": goal.icon,
        "color": goal.color,
        "notes": goal.notes,
        "is_resilient": goal.goal_type == GoalType.SAVINGS or (goal.strategy_type == GoalStrategy.CONSERVATIVE),
        "progress_percent": round(progress, 1),
        "days_remaining": days_remaining,
        "monthly_needed": monthly_needed,
        "created_at": goal.created_at,
    }


async def _owned_or_404(db: AsyncSession, goal_id: UUID, user: User) -> Goal:
    goal = await find_owned_goal(db, goal_id, user.id)
    if not goal:
        raise HTTPException(status_code=404, detail=GOAL_NOT_FOUND)
    return goal


def _parse_create_deadline(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Format de date invalide, attendu YYYY-MM-DD",
        ) from exc


@router.get("", response_model=list[GoalResponse])
async def list_goals(user: CurrentUser, session: Session, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    goals = await list_user_goals(session, user.id, skip, limit)
    return [_build_response(g) for g in goals]


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(data: GoalCreate, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Refuse un nom de liquidité (400) ; un objectif SAVINGS est toujours prudent ; ``current_amount`` part de la
    valeur actuelle du portefeuille."""
    if is_cash_like(data.name.strip().upper()):
        raise HTTPException(
            status_code=400,
            detail=(
                "La liquidité n'est pas un actif d'investissement. Utilisez un objectif de type 'Épargne de Sécurité'."
            ),
        )

    deadline = _parse_create_deadline(data.deadline_date)

    strategy = data.strategy_type
    if data.goal_type == GoalType.SAVINGS:
        strategy = GoalStrategy.CONSERVATIVE

    goal = Goal(
        user_id=user.id,
        goal_type=data.goal_type,
        name=data.name,
        target_amount=data.target_amount,
        currency=data.currency,
        target_date=data.target_date,
        deadline_date=deadline,
        priority=data.priority,
        strategy_type=strategy,
        icon=data.icon,
        color=data.color,
        notes=data.notes,
    )

    try:
        session.add(goal)
        await session.commit()
        await session.refresh(goal)
    except Exception as e:
        await session.rollback()
        logger.error("Failed to create goal: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create goal") from e

    await initial_sync(session, goal, user.id)

    return _build_response(goal)


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(goal_id: UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    goal = await _owned_or_404(session, goal_id, user)
    return _build_response(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(goal_id: UUID, data: GoalUpdate, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Seuls les champs de ``GoalUpdate`` sont modifiables ; un objectif actif atteint passe en REACHED."""
    goal = await _owned_or_404(session, goal_id, user)

    update_data = data.model_dump(exclude_unset=True)
    if "deadline_date" in update_data and update_data["deadline_date"] is not None:
        try:
            update_data["deadline_date"] = date.fromisoformat(update_data["deadline_date"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Format de date invalide") from exc
    for field_name, value in update_data.items():
        if field_name in _PATCHABLE_FIELDS:
            setattr(goal, field_name, value)

    if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
        goal.status = GoalStatus.REACHED

    await session.commit()
    await session.refresh(goal)
    return _build_response(goal)


@router.post("/{goal_id}/sync", response_model=GoalResponse)
async def sync_goal_with_portfolio(goal_id: UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Recale ``current_amount`` sur la valeur réelle du portefeuille, comme le cron quotidien."""
    goal = await _owned_or_404(session, goal_id, user)

    await sync_goals_for_user(session, user.id, only_goal_id=goal.id)
    await session.refresh(goal)
    return _build_response(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(goal_id: UUID, user: CurrentUser, session: Session) -> None:
    goal = await _owned_or_404(session, goal_id, user)

    await session.delete(goal)
    await session.commit()


@router.get("/{goal_id}/projection", response_model=GoalProjectionResponse)
async def get_goal_projection(
    goal_id: UUID,
    user: CurrentUser,
    session: Session,
    monthly_contribution: Annotated[float, Query(ge=0, description="Monthly DCA contribution (€)")] = 0.0,
) -> GoalProjectionResponse:
    """Projection Monte Carlo : probabilité d'atteinte, effort mensuel requis et courbe p25/p50/p75, coupons de
    crowdfunding des 60 prochains mois inclus ; un objectif SAVINGS est toujours projeté en prudent."""
    goal = await _owned_or_404(session, goal_id, user)

    if goal.goal_type == GoalType.SAVINGS:
        strategy = "conservative"
    else:
        strategy = goal.strategy_type.value.lower() if goal.strategy_type else "moderate"

    coupon_income = await crowdfunding_calendar_service.get_upcoming_coupon_income(session, user.id, months_ahead=60)

    projection = await goal_projection_service.project_goal(
        db=session,
        user_id=str(user.id),
        goal_id=str(goal.id),
        current_amount=float(goal.current_amount),
        target_amount=float(goal.target_amount),
        deadline=goal.deadline_date,
        strategy_type=strategy,
        monthly_contribution=monthly_contribution,
        coupon_income=coupon_income,
    )

    return GoalProjectionResponse(
        goal_id=projection.goal_id,
        current_amount=projection.current_amount,
        target_amount=projection.target_amount,
        months_remaining=projection.months_remaining,
        rmc=projection.rmc,
        rmc_with_returns=projection.rmc_with_returns,
        probability_on_track=projection.probability_on_track,
        probability_label=projection.probability_label,
        alert_message=projection.alert_message,
        regime_label=projection.regime_label,
        strategy_type=projection.strategy_type,
        gold_shield_active=projection.gold_shield_active,
        eta_date=projection.eta_date,
        eta_months=projection.eta_months,
        gold_shield_advice=projection.gold_shield_advice,
        curve=[
            ProjectionPointResponse(
                month=p.month,
                date_label=p.date_label,
                projected_p50=p.projected_p50,
                projected_p25=p.projected_p25,
                projected_p75=p.projected_p75,
                target_line=p.target_line,
            )
            for p in projection.curve
        ],
    )
