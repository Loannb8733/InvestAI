"""API Key schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class APIKeyBase(BaseModel):
    """Base API key schema."""

    exchange: str = Field(..., max_length=50)
    label: str | None = Field(None, max_length=100)


class APIKeyCreate(APIKeyBase):
    """Schema for creating an API key."""

    api_key: str = Field(..., min_length=1)
    secret_key: str | None = None
    passphrase: str | None = None


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    label: str | None = Field(None, max_length=100)
    api_key: str | None = None
    secret_key: str | None = None
    passphrase: str | None = None
    is_active: bool | None = None


class APIKeyResponse(APIKeyBase):
    """Schema for API key response (no sensitive data)."""

    id: UUID
    is_active: bool
    status: str = "active"
    error_count: int = 0
    last_sync_at: datetime | None
    last_error: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyTestResult(BaseModel):
    """Result of testing an API key connection."""

    success: bool
    message: str
    balance: dict | None = None


class ExchangeInfo(BaseModel):
    """Information about a supported exchange."""

    id: str
    name: str
    requires_secret: bool
    requires_passphrase: bool
    description: str
