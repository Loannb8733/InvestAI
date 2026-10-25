from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

FLAT_TAX = 0.30


class GuaranteeInfo(BaseModel):
    type: str
    rank: str | None = None
    description: str
    strength: str


class ProjectAuditResponse(BaseModel):
    id: UUID
    project_id: UUID | None = None
    file_names: list[str]
    document_type: str | None = None
    project_name: str | None = None
    operator: str | None = None
    location: str | None = None
    tri: float | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    collection_amount: float | None = None
    margin_percent: float | None = None
    ltv: float | None = None
    ltc: float | None = None
    pre_sales_percent: float | None = None
    equity_contribution: float | None = None
    guarantees: list[GuaranteeInfo] = []
    admin_status: str | None = None
    score_operator: int | None = None
    score_location: int | None = None
    score_guarantees: int | None = None
    score_risk_return: int | None = None
    score_admin: int | None = None
    risk_score: int | None = None
    points_forts: list[str] = []
    points_vigilance: list[str] = []
    red_flags: list[str] = []
    verdict: str = "VIGILANCE"
    suggested_investment: float | None = None
    diversification_impact: str | None = None
    correlation_score: float | None = None
    portfolio_concentration: dict[str, Any] | None = None
    analysis_source: str | None = None
    created_at: datetime

    @field_validator("guarantees", "points_forts", "points_vigilance", "red_flags", mode="before")
    @classmethod
    def none_to_list(cls, value: Any) -> Any:
        """Une liste absente en base devient vide."""
        return value if value is not None else []

    @field_validator("verdict", mode="before")
    @classmethod
    def none_to_default_verdict(cls, value: Any) -> Any:
        """Un verdict absent vaut « VIGILANCE »."""
        return value if value is not None else "VIGILANCE"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def investment_simulation(self) -> dict[str, Any] | None:
        """Rendement du placement suggéré sur la durée moyenne annoncée, au PFU de 30 %."""
        if self.suggested_investment is None or self.tri is None:
            return None
        invest = self.suggested_investment
        duration_min = self.duration_min or 12
        duration = (duration_min + (self.duration_max or duration_min)) / 2.0
        tri_rate = self.tri / 100.0
        gross_interest = round(invest * tri_rate * (duration / 12.0), 2)
        net_interest = round(gross_interest * (1 - FLAT_TAX), 2)
        return {
            "investment_amount": invest,
            "duration_months": round(duration),
            "tri_percent": self.tri,
            "gross_interest": gross_interest,
            "tax_amount": round(gross_interest * FLAT_TAX, 2),
            "net_interest": net_interest,
            "monthly_gross_return": round(gross_interest / duration, 2) if duration > 0 else 0,
            "total_at_end": round(invest + net_interest, 2),
            "roi_net_percent": round((net_interest / invest) * 100, 2) if invest > 0 else 0,
        }

    model_config = ConfigDict(from_attributes=True)
