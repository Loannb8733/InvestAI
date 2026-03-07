"""Pydantic schemas for crowdfunding projects."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.crowdfunding_project import ProjectStatus, RepaymentType

# ---------- Request schemas ----------


class CrowdfundingProjectCreate(BaseModel):
    portfolio_id: UUID
    platform: str = Field(..., max_length=100)
    project_name: str = Field(..., max_length=300)
    description: Optional[str] = None
    project_url: Optional[str] = Field(None, max_length=500)
    invested_amount: Decimal = Field(..., ge=0)
    annual_rate: Decimal = Field(..., ge=0, le=100)
    duration_months: int = Field(..., ge=1, le=360)
    repayment_type: RepaymentType = RepaymentType.IN_FINE
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    status: ProjectStatus = ProjectStatus.ACTIVE


class CrowdfundingProjectUpdate(BaseModel):
    project_name: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    project_url: Optional[str] = Field(None, max_length=500)
    platform: Optional[str] = Field(None, max_length=100)
    annual_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    duration_months: Optional[int] = Field(None, ge=1, le=360)
    repayment_type: Optional[RepaymentType] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    total_received: Optional[Decimal] = Field(None, ge=0)


# ---------- Response schemas ----------


class CrowdfundingProjectResponse(BaseModel):
    id: UUID
    asset_id: UUID
    platform: str
    project_name: Optional[str] = None
    description: Optional[str] = None
    project_url: Optional[str] = None
    invested_amount: Decimal
    annual_rate: Decimal
    duration_months: int
    repayment_type: RepaymentType
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: ProjectStatus
    total_received: Decimal
    created_at: datetime
    updated_at: datetime

    # Computed
    projected_total_interest: Optional[float] = None
    interest_earned: Optional[float] = None
    progress_percent: Optional[float] = None

    class Config:
        from_attributes = True


class CrowdfundingDashboardResponse(BaseModel):
    total_invested: float
    total_received: float
    projected_annual_interest: float
    weighted_average_rate: float
    active_count: int
    completed_count: int
    delayed_count: int
    defaulted_count: int
    funding_count: int
    next_maturity: Optional[date] = None
    platform_breakdown: dict[str, float]
    projects: list[CrowdfundingProjectResponse]


# ---------- Audit Lab schemas ----------


class GuaranteeInfo(BaseModel):
    type: str
    rank: Optional[str] = None
    description: str
    strength: str  # "forte", "moyenne", "faible"


class ProjectAuditResponse(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    file_names: list[str]
    document_type: Optional[str] = None
    project_name: Optional[str] = None
    operator: Optional[str] = None
    location: Optional[str] = None
    tri: Optional[float] = None
    duration_min: Optional[int] = None
    duration_max: Optional[int] = None
    collection_amount: Optional[float] = None
    margin_percent: Optional[float] = None
    ltv: Optional[float] = None
    ltc: Optional[float] = None
    pre_sales_percent: Optional[float] = None
    equity_contribution: Optional[float] = None
    guarantees: list[GuaranteeInfo] = []
    admin_status: Optional[str] = None
    score_operator: Optional[int] = None
    score_location: Optional[int] = None
    score_guarantees: Optional[int] = None
    score_risk_return: Optional[int] = None
    score_admin: Optional[int] = None
    risk_score: Optional[int] = None
    points_forts: list[str] = []
    points_vigilance: list[str] = []
    red_flags: list[str] = []
    verdict: str = "VIGILANCE"
    suggested_investment: Optional[float] = None
    diversification_impact: Optional[str] = None
    correlation_score: Optional[float] = None
    portfolio_concentration: Optional[dict] = None
    created_at: datetime

    @field_validator("guarantees", "points_forts", "points_vigilance", "red_flags", mode="before")
    @classmethod
    def none_to_list(cls, v):  # noqa: N805
        return v if v is not None else []

    @field_validator("verdict", mode="before")
    @classmethod
    def none_to_default_verdict(cls, v):  # noqa: N805
        return v if v is not None else "VIGILANCE"

    class Config:
        from_attributes = True
