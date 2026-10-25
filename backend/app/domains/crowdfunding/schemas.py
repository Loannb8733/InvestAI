from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.crowdfunding.models import PaymentType, ProjectStatus, RepaymentType
from app.schemas._money import Money


class CrowdfundingProjectCreate(BaseModel):
    portfolio_id: UUID | None = None
    platform: str = Field(..., max_length=100)
    project_name: str = Field(..., max_length=300)
    description: str | None = None
    project_url: str | None = Field(None, max_length=500)
    invested_amount: Money = Field(..., ge=0)
    annual_rate: Money = Field(..., ge=0, le=100)
    duration_months: int = Field(..., ge=1, le=360)
    repayment_type: RepaymentType = RepaymentType.IN_FINE
    start_date: date | None = None
    estimated_end_date: date | None = None
    interest_frequency: str | None = Field("at_maturity", max_length=20)
    tax_rate: Money = Field(Decimal("30.00"), ge=0, le=100)
    delay_months: int = Field(0, ge=0, le=120)
    status: ProjectStatus = ProjectStatus.ACTIVE


class CrowdfundingProjectUpdate(BaseModel):
    project_name: str | None = Field(None, max_length=300)
    description: str | None = None
    project_url: str | None = Field(None, max_length=500)
    platform: str | None = Field(None, max_length=100)
    invested_amount: Money | None = Field(None, gt=0)
    annual_rate: Money | None = Field(None, ge=0, le=100)
    duration_months: int | None = Field(None, ge=1, le=360)
    repayment_type: RepaymentType | None = None
    start_date: date | None = None
    estimated_end_date: date | None = None
    actual_end_date: date | None = None
    status: ProjectStatus | None = None
    interest_frequency: str | None = Field(None, max_length=20)
    tax_rate: Money | None = Field(None, ge=0, le=100)
    delay_months: int | None = Field(None, ge=0, le=120)
    total_received: Money | None = Field(None, ge=0)


class RepaymentCreate(BaseModel):
    payment_date: date
    amount: Money = Field(..., gt=0)
    payment_type: PaymentType
    interest_amount: Money | None = Field(None, ge=0)
    capital_amount: Money | None = Field(None, ge=0)
    tax_amount: Money | None = Field(None, ge=0)
    notes: str | None = None


class RepaymentResponse(BaseModel):
    id: UUID
    project_id: UUID
    payment_date: date
    amount: Money
    payment_type: PaymentType
    interest_amount: Money | None = None
    capital_amount: Money | None = None
    tax_amount: Money | None = None
    notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectDocumentResponse(BaseModel):
    id: UUID
    project_id: UUID
    file_name: str
    file_size: int
    audit_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentScheduleEntryResponse(BaseModel):
    """Échéance ; ``status`` vaut « paid », « pending » ou « overdue »."""

    id: UUID
    project_id: UUID
    due_date: date
    expected_capital: Money
    expected_interest: Money
    is_completed: bool
    completed_at: datetime | None = None
    repayment_id: UUID | None = None
    status: str = "pending"

    model_config = ConfigDict(from_attributes=True)


class CrowdfundingProjectResponse(BaseModel):
    """Projet et ses calculs ; ``projected_interest_gross`` est brut, ``projected_total_interest`` net d'impôt."""

    id: UUID
    asset_id: UUID
    platform: str
    project_name: str | None = None
    description: str | None = None
    project_url: str | None = None
    invested_amount: Money
    annual_rate: Money
    duration_months: int
    repayment_type: RepaymentType
    interest_frequency: str | None = "at_maturity"
    tax_rate: Money = Decimal("30.00")
    delay_months: int = 0
    start_date: date | None = None
    estimated_end_date: date | None = None
    actual_end_date: date | None = None
    status: ProjectStatus
    total_received: Money
    created_at: datetime
    updated_at: datetime
    projected_total_interest: float | None = None
    projected_interest_gross: float | None = None
    interest_earned: float | None = None
    progress_percent: float | None = None
    documents: list[ProjectDocumentResponse] = []
    repayments: list[RepaymentResponse] = []
    schedule: list[PaymentScheduleEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CrowdfundingDashboardResponse(BaseModel):
    """Synthèse de la poche : intérêts (P&L) séparés du capital remboursé, CRD hors projets en défaut."""

    total_invested: float
    total_received: float
    total_interest_received: float = 0.0
    total_interest_net: float = 0.0
    total_capital_repaid: float = 0.0
    capital_outstanding: float = 0.0
    defaulted_outstanding: float = 0.0
    total_referral: float = 0.0
    projected_annual_interest: float
    weighted_average_rate: float
    active_count: int
    completed_count: int
    delayed_count: int
    defaulted_count: int
    funding_count: int
    next_maturity: date | None = None
    platform_breakdown: dict[str, float]
    platform_breakdown_outstanding: dict[str, float] = Field(default_factory=dict)
    projects: list[CrowdfundingProjectResponse]


class CashflowProjectAmount(BaseModel):
    name: str
    amount: float


class CashflowMonthResponse(BaseModel):
    """Échéances non soldées d'un mois (« YYYY-MM »), tous projets hors défaut confondus."""

    month: str
    expected_capital: float = 0.0
    expected_interest: float = 0.0
    total: float = 0.0
    projects: list[CashflowProjectAmount] = Field(default_factory=list)


class TaxReportPlatform(BaseModel):
    """Intérêts annuels d'une plateforme ; withholding_gap : retenue à plus de 1 € du PFU théorique."""

    platform: str
    gross_interest: float
    tax_withheld: float
    net_interest: float
    theoretical_pfu: float
    withholding_gap: bool
    nb_payments: int


class CrowdfundingTaxReportResponse(BaseModel):
    year: int
    platforms: list[TaxReportPlatform]
    total_gross_interest: float
    total_tax_withheld: float
    total_net_interest: float
    total_theoretical_pfu: float
    nb_payments: int


class StressTestCashflowSchema(BaseModel):
    date: date
    capital: float
    interest: float
    total: float
    is_delayed: bool


class StressTestResponse(BaseModel):
    project_id: UUID
    delay_months: int
    base_irr: float | None = None
    stressed_irr: float | None = None
    irr_delta: float | None = None
    cashflows: list[StressTestCashflowSchema]
