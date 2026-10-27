from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domains.alerts.models import AUTO_THRESHOLD_CONDITIONS, PORTFOLIO_CONDITIONS, AlertCondition


class AlertCreate(BaseModel):
    """Alerte à créer : un seuil positif sauf conditions calculées, un actif sauf conditions de portefeuille."""

    asset_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=100)
    condition: AlertCondition
    threshold: float = Field(default=0, ge=0)
    currency: str = Field(default="EUR", max_length=10)
    notify_email: bool = True
    notify_in_app: bool = True

    @model_validator(mode="after")
    def validate_threshold(self) -> Self:
        """Refuse un seuil nul là où il est requis, et un actif absent ou superflu."""
        if self.condition not in AUTO_THRESHOLD_CONDITIONS and self.threshold <= 0:
            raise ValueError("Le seuil doit être supérieur à 0 pour cette condition")
        if self.condition in PORTFOLIO_CONDITIONS:
            if self.asset_id is not None:
                raise ValueError("Une alerte de portefeuille ne cible pas un actif")
        elif self.asset_id is None:
            raise ValueError("Un actif est requis pour cette condition")
        return self


class AlertUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    threshold: float | None = Field(None, gt=0)
    is_active: bool | None = None
    notify_email: bool | None = None
    notify_in_app: bool | None = None


class AlertResponse(BaseModel):
    id: UUID
    asset_id: UUID | None
    name: str
    condition: str
    threshold: float
    currency: str
    is_active: bool
    triggered_at: str | None
    triggered_count: int
    notify_email: bool
    notify_in_app: bool
    created_at: datetime
    asset_symbol: str | None = None
    asset_name: str | None = None


class AlertTriggerResponse(BaseModel):
    alert_id: UUID
    alert_name: str
    symbol: str
    condition: str
    threshold: float
    current_value: float
    triggered_at: str
    message: str


class AlertSummaryResponse(BaseModel):
    total_alerts: int
    active_alerts: int
    triggered_today: int
    total_triggers: int


class AlertConditionInfo(BaseModel):
    """Condition proposée à l'écran ; ``is_portfolio`` masque le choix d'actif, ``threshold_unit`` guide la saisie."""

    value: str
    label: str
    description: str
    is_portfolio: bool = False
    threshold_unit: str | None = None
