"""Pydantic schemas for crowdfunding projects."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.crowdfunding_project import ProjectStatus, RepaymentType
from app.models.crowdfunding_repayment import PaymentType
from app.schemas._money import Money

# ---------- Request schemas ----------


class CrowdfundingProjectCreate(BaseModel):
    portfolio_id: Optional[UUID] = None
    platform: str = Field(..., max_length=100)
    project_name: str = Field(..., max_length=300)
    description: Optional[str] = None
    project_url: Optional[str] = Field(None, max_length=500)
    invested_amount: Money = Field(..., ge=0)
    annual_rate: Money = Field(..., ge=0, le=100)
    duration_months: int = Field(..., ge=1, le=360)
    repayment_type: RepaymentType = RepaymentType.IN_FINE
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    interest_frequency: Optional[str] = Field("at_maturity", max_length=20)
    tax_rate: Money = Field(Decimal("30.00"), ge=0, le=100)
    delay_months: int = Field(0, ge=0, le=120)
    status: ProjectStatus = ProjectStatus.ACTIVE


class CrowdfundingProjectUpdate(BaseModel):
    project_name: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    project_url: Optional[str] = Field(None, max_length=500)
    platform: Optional[str] = Field(None, max_length=100)
    invested_amount: Optional[Money] = Field(None, gt=0)
    annual_rate: Optional[Money] = Field(None, ge=0, le=100)
    duration_months: Optional[int] = Field(None, ge=1, le=360)
    repayment_type: Optional[RepaymentType] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    interest_frequency: Optional[str] = Field(None, max_length=20)
    tax_rate: Optional[Money] = Field(None, ge=0, le=100)
    delay_months: Optional[int] = Field(None, ge=0, le=120)
    total_received: Optional[Money] = Field(None, ge=0)


# ---------- Repayment schemas ----------


class RepaymentCreate(BaseModel):
    payment_date: date
    amount: Money = Field(..., gt=0)
    payment_type: PaymentType
    interest_amount: Optional[Money] = Field(None, ge=0)
    capital_amount: Optional[Money] = Field(None, ge=0)
    tax_amount: Optional[Money] = Field(None, ge=0)
    notes: Optional[str] = None


class RepaymentResponse(BaseModel):
    id: UUID
    project_id: UUID
    payment_date: date
    amount: Money
    payment_type: PaymentType
    interest_amount: Optional[Money] = None
    capital_amount: Optional[Money] = None
    tax_amount: Optional[Money] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Response schemas ----------


class ProjectDocumentResponse(BaseModel):
    id: UUID
    project_id: UUID
    file_name: str
    file_size: int
    audit_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentScheduleEntryResponse(BaseModel):
    id: UUID
    project_id: UUID
    due_date: date
    expected_capital: Money
    expected_interest: Money
    is_completed: bool
    completed_at: Optional[datetime] = None
    repayment_id: Optional[UUID] = None
    status: str = "pending"  # "paid" | "pending" | "overdue"

    class Config:
        from_attributes = True


class CrowdfundingProjectResponse(BaseModel):
    id: UUID
    asset_id: UUID
    platform: str
    project_name: Optional[str] = None
    description: Optional[str] = None
    project_url: Optional[str] = None
    invested_amount: Money
    annual_rate: Money
    duration_months: int
    repayment_type: RepaymentType
    interest_frequency: Optional[str] = "at_maturity"
    tax_rate: Money = Decimal("30.00")
    delay_months: int = 0
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: ProjectStatus
    total_received: Money
    created_at: datetime
    updated_at: datetime

    # Computed
    projected_total_interest: Optional[float] = None
    # Intérêts projetés BRUTS de fiscalité (invested × rate × months/12) —
    # permet des ratios homogènes brut/brut face à interest_earned (brut).
    projected_interest_gross: Optional[float] = None
    interest_earned: Optional[float] = None
    progress_percent: Optional[float] = None
    documents: list[ProjectDocumentResponse] = []
    repayments: list[RepaymentResponse] = []
    schedule: list[PaymentScheduleEntryResponse] = []

    class Config:
        from_attributes = True


class CrowdfundingDashboardResponse(BaseModel):
    total_invested: float
    total_received: float
    # Décomposition comptable : les intérêts sont du P&L, le capital remboursé
    # est un retour de principal ; le CRD (capital restant dû) est la valeur
    # de la poche ; le principal des projets en défaut est provisionné à part.
    total_interest_received: float = 0.0
    total_capital_repaid: float = 0.0
    capital_outstanding: float = 0.0
    defaulted_outstanding: float = 0.0
    # Bonus de parrainage / plateforme encaissés (hors intérêts et hors capital).
    total_referral: float = 0.0
    projected_annual_interest: float
    weighted_average_rate: float
    active_count: int
    completed_count: int
    delayed_count: int
    defaulted_count: int
    funding_count: int
    next_maturity: Optional[date] = None
    platform_breakdown: dict[str, float]
    # Exposition par plateforme au capital restant dû (projets en défaut
    # exclus) — un projet remboursé à 80 % ne pèse plus que 20 %.
    platform_breakdown_outstanding: dict[str, float] = Field(default_factory=dict)
    projects: list[CrowdfundingProjectResponse]


# ---------- Cashflow schedule (échéancier consolidé) ----------


class CashflowProjectAmount(BaseModel):
    """Contribution d'un projet au cash-flow d'un mois (montant BRUT de fiscalité)."""

    name: str
    amount: float


class CashflowMonthResponse(BaseModel):
    """Cash-flows attendus sur un mois, agrégés sur tous les projets non-défaut.

    Somme des échéances contractuelles NON complétées (capital + intérêts).
    Les montants sont BRUTS de fiscalité — les échéanciers sont contractuels,
    avant prélèvements.
    """

    month: str  # "YYYY-MM"
    expected_capital: float = 0.0
    expected_interest: float = 0.0
    total: float = 0.0
    projects: list[CashflowProjectAmount] = Field(default_factory=list)


# ---------- Rapport fiscal annuel (réconciliation IFU) ----------


class TaxReportPlatform(BaseModel):
    """Agrégat fiscal annuel d'une plateforme.

    Les intérêts de crowdfunding immobilier (obligations) sont des revenus de
    capitaux mobiliers soumis au PFU 30 % (12,8 % IR + 17,2 % PS), prélevé À LA
    SOURCE par la plateforme (le ``tax_amount`` saisi sur chaque versement) et
    déclaré case 2TR/2BH via l'IFU (formulaire 2561) qu'elle envoie. Ce rapport
    sert à réconcilier ces IFU avec les versements saisis dans l'app.

    ``withholding_gap`` : True quand la retenue saisie diverge de plus de 1 €
    du PFU théorique (``gross_interest × 0.30``) — soit une dispense d'acompte
    (12,8 % IR non prélevé sur demande, revenu fiscal de référence sous les
    seuils), soit des versements enregistrés sans le split fiscal renseigné.
    """

    platform: str
    # Intérêts bruts encaissés dans l'année (avant prélèvements)
    gross_interest: float
    # Retenue à la source saisie sur les versements (somme des tax_amount)
    tax_withheld: float
    # Net perçu = brut − retenues
    net_interest: float
    # PFU théorique : gross_interest × 30 %
    theoretical_pfu: float
    withholding_gap: bool
    nb_payments: int


class CrowdfundingTaxReportResponse(BaseModel):
    """Rapport fiscal annuel agrégé par plateforme + totaux."""

    year: int
    platforms: list[TaxReportPlatform]
    total_gross_interest: float
    total_tax_withheld: float
    total_net_interest: float
    total_theoretical_pfu: float
    nb_payments: int


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

    @computed_field  # type: ignore[misc]
    @property
    def investment_simulation(self) -> Optional[dict]:
        """Compute investment simulation from audit data."""
        if self.suggested_investment is None or self.tri is None:
            return None

        invest = self.suggested_investment
        tri_pct = self.tri / 100.0
        dur_min = self.duration_min or 12
        dur_max = self.duration_max or dur_min
        dur_avg = (dur_min + dur_max) / 2.0
        tax_rate = 0.30  # Flat tax France

        gross_interest = round(invest * tri_pct * (dur_avg / 12.0), 2)
        net_interest = round(gross_interest * (1 - tax_rate), 2)
        monthly_gross = round(gross_interest / dur_avg, 2) if dur_avg > 0 else 0
        total_at_end = round(invest + net_interest, 2)

        return {
            "investment_amount": invest,
            "duration_months": round(dur_avg),
            "tri_percent": self.tri,
            "gross_interest": gross_interest,
            "tax_amount": round(gross_interest * tax_rate, 2),
            "net_interest": net_interest,
            "monthly_gross_return": monthly_gross,
            "total_at_end": total_at_end,
            "roi_net_percent": round((net_interest / invest) * 100, 2) if invest > 0 else 0,
        }

    class Config:
        from_attributes = True


# ---------- Stress Test schemas ----------


class StressTestCashflowSchema(BaseModel):
    date: date
    capital: float
    interest: float
    total: float
    is_delayed: bool


class StressTestResponse(BaseModel):
    project_id: UUID
    delay_months: int
    base_irr: Optional[float] = None
    stressed_irr: Optional[float] = None
    irr_delta: Optional[float] = None
    cashflows: list[StressTestCashflowSchema]
