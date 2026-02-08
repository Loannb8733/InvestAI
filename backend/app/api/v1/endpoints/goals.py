"""Financial goals endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.goal import Goal, GoalStatus
from app.models.user import User

router = APIRouter()


# ---- Schemas ----

class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=10)
    target_date: Optional[str] = None
    icon: str = Field(default="target", max_length=50)
    color: str = Field(default="#6366f1", max_length=7)
    notes: Optional[str] = None


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_amount: Optional[Decimal] = Field(None, gt=0)
    current_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    target_date: Optional[str] = None
    status: Optional[GoalStatus] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
    notes: Optional[str] = None


class GoalResponse(BaseModel):
    id: UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_date: Optional[str]
    status: GoalStatus
    icon: str
    color: str
    notes: Optional[str]
    progress_percent: float
    days_remaining: Optional[int]
    monthly_needed: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


def _build_response(goal: Goal) -> dict:
    """Build goal response with computed fields."""
    progress = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
    progress = min(progress, 100.0)

    days_remaining = None
    monthly_needed = None
    if goal.target_date:
        try:
            target = date.fromisoformat(goal.target_date)
            delta = (target - date.today()).days
            days_remaining = max(delta, 0)
            remaining_amount = float(goal.target_amount - goal.current_amount)
            if remaining_amount > 0 and days_remaining > 0:
                months_left = days_remaining / 30.44
                monthly_needed = round(remaining_amount / months_left, 2) if months_left > 0 else None
        except ValueError:
            pass

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "currency": goal.currency,
        "target_date": goal.target_date,
        "status": goal.status,
        "icon": goal.icon,
        "color": goal.color,
        "notes": goal.notes,
        "progress_percent": round(progress, 1),
        "days_remaining": days_remaining,
        "monthly_needed": monthly_needed,
        "created_at": goal.created_at,
    }


@router.get("/", response_model=List[GoalResponse])
async def list_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all goals for the current user."""
    result = await db.execute(
        select(Goal)
        .where(Goal.user_id == current_user.id)
        .order_by(Goal.created_at.desc())
    )
    goals = result.scalars().all()
    return [_build_response(g) for g in goals]


@router.post("/", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new financial goal."""
    goal = Goal(
        user_id=current_user.id,
        name=data.name,
        target_amount=data.target_amount,
        currency=data.currency,
        target_date=data.target_date,
        icon=data.icon,
        color=data.color,
        notes=data.notes,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return _build_response(goal)


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific goal."""
    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _build_response(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: UUID,
    data: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a goal."""
    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)

    # Auto-mark as reached
    if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
        goal.status = GoalStatus.REACHED

    await db.commit()
    await db.refresh(goal)
    return _build_response(goal)


@router.post("/{goal_id}/sync", response_model=GoalResponse)
async def sync_goal_with_portfolio(
    goal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync goal's current_amount with actual portfolio value."""
    from app.models.asset import Asset
    from app.models.portfolio import Portfolio
    from app.services.price_service import PriceService

    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Calculate total portfolio value
    portfolios_result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolios = portfolios_result.scalars().all()

    total_value = Decimal("0")
    price_service = PriceService()
    for portfolio in portfolios:
        assets_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio.id,
            )
        )
        assets = assets_result.scalars().all()
        for asset in assets:
            if float(asset.quantity) > 0:
                price = await price_service.get_price(asset.symbol, asset.asset_type.value)
                total_value += asset.quantity * Decimal(str(price))

    goal.current_amount = total_value
    if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
        goal.status = GoalStatus.REACHED

    await db.commit()
    await db.refresh(goal)
    return _build_response(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a goal."""
    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    await db.delete(goal)
    await db.commit()
