"""Financial goals endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.goal import Goal, GoalPriority, GoalStatus, GoalStrategy, GoalType
from app.models.user import User

router = APIRouter()


# ---- Schemas ----


class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    goal_type: GoalType = GoalType.ASSET
    target_amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=10)
    target_date: Optional[str] = None
    deadline_date: Optional[str] = None  # ISO date "2026-12-31"
    priority: GoalPriority = GoalPriority.MEDIUM
    strategy_type: GoalStrategy = GoalStrategy.MODERATE
    icon: str = Field(default="target", max_length=50)
    color: str = Field(default="#6366f1", max_length=7)
    notes: Optional[str] = None

    @field_validator("goal_type", mode="before")
    @classmethod
    def norm_goal_type(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("priority", mode="before")
    @classmethod
    def norm_priority(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("strategy_type", mode="before")
    @classmethod
    def norm_strategy(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    goal_type: Optional[GoalType] = None
    target_amount: Optional[Decimal] = Field(None, gt=0)
    current_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    target_date: Optional[str] = None
    deadline_date: Optional[str] = None
    priority: Optional[GoalPriority] = None
    strategy_type: Optional[GoalStrategy] = None
    status: Optional[GoalStatus] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
    notes: Optional[str] = None

    @field_validator("goal_type", mode="before")
    @classmethod
    def norm_goal_type(cls, v: str | None) -> str | None:
        return v.upper() if isinstance(v, str) else v

    @field_validator("priority", mode="before")
    @classmethod
    def norm_priority(cls, v: str | None) -> str | None:
        return v.upper() if isinstance(v, str) else v

    @field_validator("strategy_type", mode="before")
    @classmethod
    def norm_strategy(cls, v: str | None) -> str | None:
        return v.upper() if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def norm_status(cls, v: str | None) -> str | None:
        return v.upper() if isinstance(v, str) else v


class GoalResponse(BaseModel):
    id: UUID
    goal_type: str = "asset"
    name: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    target_date: Optional[str]
    deadline_date: Optional[str]
    priority: str
    strategy_type: str
    status: str
    icon: str
    color: str
    notes: Optional[str]
    is_resilient: bool = False
    progress_percent: float
    days_remaining: Optional[int]
    monthly_needed: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectionPointResponse(BaseModel):
    month: int
    date_label: str
    projected_p50: float
    projected_p25: float
    projected_p75: float
    target_line: float


class GoalProjectionResponse(BaseModel):
    goal_id: str
    current_amount: float
    target_amount: float
    months_remaining: int
    rmc: float
    rmc_with_returns: float
    probability_on_track: float
    probability_label: str
    alert_message: Optional[str]
    regime_label: str
    strategy_type: str
    gold_shield_active: bool
    eta_date: Optional[str]
    eta_months: int
    gold_shield_advice: Optional[str]
    curve: List[ProjectionPointResponse]


def _build_response(goal: Goal) -> dict:
    """Build goal response with computed fields."""
    progress = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
    progress = min(progress, 100.0)

    days_remaining = None
    monthly_needed = None
    # Use deadline_date (Date) if available, fall back to target_date (string)
    effective_date = None
    if goal.deadline_date:
        effective_date = goal.deadline_date
    elif goal.target_date:
        try:
            effective_date = date.fromisoformat(goal.target_date)
        except ValueError:
            pass

    if effective_date:
        delta = (effective_date - date.today()).days
        days_remaining = max(delta, 0)
        remaining_amount = float(goal.target_amount - goal.current_amount)
        if remaining_amount > 0 and days_remaining > 0:
            months_left = days_remaining / 30.44
            monthly_needed = round(remaining_amount / months_left, 2) if months_left > 0 else None

    return {
        "id": goal.id,
        "goal_type": goal.goal_type.value.lower() if goal.goal_type else "asset",
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "currency": goal.currency,
        "target_date": goal.target_date,
        "deadline_date": str(goal.deadline_date) if goal.deadline_date else None,
        "priority": goal.priority.value.lower() if goal.priority else "medium",
        "strategy_type": goal.strategy_type.value.lower() if goal.strategy_type else "moderate",
        "status": goal.status.value.lower() if goal.status else "active",
        "icon": goal.icon,
        "color": goal.color,
        "notes": goal.notes,
        "is_resilient": goal.goal_type == GoalType.SAVINGS or (goal.strategy_type == GoalStrategy.CONSERVATIVE),
        "progress_percent": round(progress, 1),
        "days_remaining": days_remaining,
        "monthly_needed": monthly_needed,
        "created_at": goal.created_at,
    }


@router.get("", response_model=List[GoalResponse])
async def list_goals(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all goals for the current user."""
    result = await db.execute(
        select(Goal).where(Goal.user_id == current_user.id).order_by(Goal.created_at.desc()).offset(skip).limit(limit)
    )
    goals = result.scalars().all()
    return [_build_response(g) for g in goals]


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new financial goal."""
    import logging

    from app.services.metrics_service import is_liquidity

    logger = logging.getLogger(__name__)

    # Block goals named after liquidity symbols (EUR, USD, USDT, USDC, etc.)
    if is_liquidity(data.name.strip().upper()):
        raise HTTPException(
            status_code=400,
            detail="La liquidité n'est pas un actif d'investissement. Utilisez un objectif de type 'Épargne de Sécurité'.",
        )

    deadline = None
    if data.deadline_date:
        try:
            deadline = date.fromisoformat(data.deadline_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid deadline_date format, expected YYYY-MM-DD")

    # SAVINGS goals force conservative strategy
    strategy = data.strategy_type
    if data.goal_type == GoalType.SAVINGS:
        strategy = GoalStrategy.CONSERVATIVE

    goal = Goal(
        user_id=current_user.id,
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
        db.add(goal)
        await db.commit()
        await db.refresh(goal)
    except Exception as e:
        await db.rollback()
        logger.error("Failed to create goal: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create goal")

    # Initial sync: set current_amount from actual portfolio value
    try:
        from app.models.asset import Asset
        from app.models.portfolio import Portfolio
        from app.services.price_service import PriceService

        portfolios_result = await db.execute(select(Portfolio).where(Portfolio.user_id == current_user.id))
        portfolios = portfolios_result.scalars().all()

        total_value = Decimal("0")
        price_service = PriceService()
        is_savings = goal.goal_type == GoalType.SAVINGS
        for portfolio in portfolios:
            assets_result = await db.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))
            assets = assets_result.scalars().all()
            for asset in assets:
                if float(asset.quantity) > 0:
                    if is_savings and not is_liquidity(asset.symbol):
                        continue
                    try:
                        price = await price_service.get_price(asset.symbol, asset.asset_type.value)
                        total_value += asset.quantity * Decimal(str(price))
                    except Exception:
                        pass
            if is_savings:
                for _ccy, amount in (portfolio.cash_balances or {}).items():
                    total_value += Decimal(str(amount))

        if total_value > 0:
            goal.current_amount = total_value
            if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
                goal.status = GoalStatus.REACHED
            await db.commit()
            await db.refresh(goal)
    except Exception as e:
        logger.warning("Initial goal sync failed (non-blocking): %s", e)

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

    update_data = data.model_dump(exclude_unset=True)
    # Convert deadline_date string to date object
    if "deadline_date" in update_data and update_data["deadline_date"] is not None:
        try:
            update_data["deadline_date"] = date.fromisoformat(update_data["deadline_date"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid deadline_date format")
    for field_name, value in update_data.items():
        setattr(goal, field_name, value)

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

    # Calculate total portfolio value (or liquidity-only for SAVINGS goals)
    from app.services.metrics_service import is_liquidity

    portfolios_result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolios = portfolios_result.scalars().all()

    total_value = Decimal("0")
    price_service = PriceService()
    is_savings = goal.goal_type == GoalType.SAVINGS
    for portfolio in portfolios:
        assets_result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio.id,
            )
        )
        assets = assets_result.scalars().all()
        for asset in assets:
            if float(asset.quantity) > 0:
                # SAVINGS goals only count liquidity (cash/stables/gold)
                if is_savings and not is_liquidity(asset.symbol):
                    continue
                price = await price_service.get_price(asset.symbol, asset.asset_type.value)
                total_value += asset.quantity * Decimal(str(price))
        # Include portfolio cash_balances for SAVINGS goals
        if is_savings:
            for _ccy, amount in (portfolio.cash_balances or {}).items():
                total_value += Decimal(str(amount))

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


@router.get("/{goal_id}/projection", response_model=GoalProjectionResponse)
async def get_goal_projection(
    goal_id: UUID,
    monthly_contribution: float = Query(0.0, ge=0, description="Monthly DCA contribution (€)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Monte Carlo projection for a specific goal.

    Returns probability of reaching the goal, required monthly
    contribution, and projected growth curve with confidence bands.
    """
    from app.services.crowdfunding_calendar_service import crowdfunding_calendar_service
    from app.services.goal_projection_service import goal_projection_service

    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # SAVINGS goals always use conservative strategy (liquidity-only target)
    if goal.goal_type == GoalType.SAVINGS:
        strategy = "conservative"
    else:
        strategy = goal.strategy_type.value.lower() if goal.strategy_type else "moderate"

    # Fetch upcoming coupon income from crowdfunding projects
    coupon_income = await crowdfunding_calendar_service.get_upcoming_coupon_income(db, current_user.id, months_ahead=60)

    projection = await goal_projection_service.project_goal(
        db=db,
        user_id=str(current_user.id),
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
