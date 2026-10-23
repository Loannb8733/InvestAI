from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIKeyCreate(BaseModel):
    exchange: str = Field(..., max_length=50)
    label: str | None = Field(None, max_length=100)
    api_key: str = Field(..., min_length=1)
    secret_key: str | None = None
    passphrase: str | None = None


class APIKeyUpdate(BaseModel):
    label: str | None = Field(None, max_length=100)
    api_key: str | None = None
    secret_key: str | None = None
    passphrase: str | None = None
    is_active: bool | None = None


class APIKeyResponse(BaseModel):
    id: UUID
    exchange: str
    label: str | None = None
    is_active: bool
    status: str = "active"
    error_count: int = 0
    last_sync_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    balance: dict[str, float] | None = None


class ExchangeInfo(BaseModel):
    id: str
    name: str
    requires_secret: bool
    requires_passphrase: bool
    description: str


class BalanceSyncResult(BaseModel):
    message: str
    synced_assets: int
    portfolio_id: str | None = None
    portfolio_name: str | None = None


class TaskDispatched(BaseModel):
    task_id: str
    status: Literal["dispatched"] = "dispatched"
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "completed", "failed"]
    synced: int | None = None
    message: str | None = None
    error: str | None = None


class ColdWalletCreate(BaseModel):
    """Crée ou renomme le nom d'une adresse (une seule entrée par adresse)."""

    address: str = Field(..., min_length=4, max_length=255)
    label: str = Field(..., min_length=1, max_length=50)

    @field_validator("address", "label")
    @classmethod
    def _stripped(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("address and label are required")
        return stripped


class ColdWalletResponse(BaseModel):
    id: UUID
    address: str
    label: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
