"""Pydantic schemas for strategies."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# --- Strategy ---


class StrategyActionCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    symbol: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "EUR"
    reason: Optional[str] = None


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    actions: List[StrategyActionCreate] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class StrategyActionResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    action: str
    symbol: Optional[str] = None
    amount: Optional[float] = None
    currency: str
    reason: Optional[str] = None
    status: str
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    source: str
    status: str
    params: Dict[str, Any]
    ai_reasoning: Optional[str] = None
    market_regime: Optional[str] = None
    confidence: Optional[float] = None
    actions: List[StrategyActionResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StrategyActionUpdate(BaseModel):
    status: Optional[str] = None  # EXECUTED or SKIPPED
    amount: Optional[float] = None  # Allow user to override AI-proposed amount
