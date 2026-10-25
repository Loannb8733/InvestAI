from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.planning.goals.models import GoalPriority, GoalStatus, GoalStrategy, GoalType


class GoalCreate(BaseModel):
    """Les enums s'acceptent en minuscules ; ``deadline_date`` est une date ISO (``2026-12-31``)."""

    name: str = Field(..., min_length=1, max_length=200)
    goal_type: GoalType = GoalType.ASSET
    target_amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=10)
    target_date: str | None = None
    deadline_date: str | None = None
    priority: GoalPriority = GoalPriority.MEDIUM
    strategy_type: GoalStrategy = GoalStrategy.MODERATE
    icon: str = Field(default="target", max_length=50)
    color: str = Field(default="#6366f1", max_length=7)
    notes: str | None = None

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
    name: str | None = Field(None, min_length=1, max_length=200)
    goal_type: GoalType | None = None
    target_amount: Decimal | None = Field(None, gt=0)
    current_amount: Decimal | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=10)
    target_date: str | None = None
    deadline_date: str | None = None
    priority: GoalPriority | None = None
    strategy_type: GoalStrategy | None = None
    status: GoalStatus | None = None
    icon: str | None = Field(None, max_length=50)
    color: str | None = Field(None, max_length=7)
    notes: str | None = None

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
    target_date: str | None
    deadline_date: str | None
    priority: str
    strategy_type: str
    status: str
    icon: str
    color: str
    notes: str | None
    is_resilient: bool = False
    progress_percent: float
    days_remaining: int | None
    monthly_needed: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    alert_message: str | None
    regime_label: str
    strategy_type: str
    gold_shield_active: bool
    eta_date: str | None
    eta_months: int
    gold_shield_advice: str | None
    curve: list[ProjectionPointResponse]
