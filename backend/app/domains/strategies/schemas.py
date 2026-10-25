from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.strategies.models import ActionStatus, StrategyStatus


class StrategyActionCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    symbol: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    reason: str | None = None


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    actions: list[StrategyActionCreate] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: StrategyStatus | None = None
    params: dict[str, Any] | None = None


class StrategyActionResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    action: str
    symbol: str | None = None
    amount: float | None = None
    currency: str
    reason: str | None = None
    status: str
    scheduled_at: datetime | None = None
    executed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    source: str
    status: str
    params: dict[str, Any]
    ai_reasoning: str | None = None
    market_regime: str | None = None
    confidence: float | None = None
    actions: list[StrategyActionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyActionUpdate(BaseModel):
    """Statut ``EXECUTED`` ou ``SKIPPED`` ; ``amount`` remplace le montant proposé par l'IA."""

    status: ActionStatus | None = None
    amount: float | None = None
