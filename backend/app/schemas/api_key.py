"""API Key schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class APIKeyBase(BaseModel):
    """Base API key schema."""

    exchange: str = Field(..., max_length=50)
    label: Optional[str] = Field(None, max_length=100)


class APIKeyCreate(APIKeyBase):
    """Schema for creating an API key."""

    api_key: str = Field(..., min_length=1)
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    label: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None
    is_active: Optional[bool] = None


class APIKeyResponse(APIKeyBase):
    """Schema for API key response (no sensitive data)."""

    id: UUID
    is_active: bool
    last_sync_at: Optional[str]
    last_error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyTestResult(BaseModel):
    """Result of testing an API key connection."""

    success: bool
    message: str
    balance: Optional[dict] = None


class ExchangeInfo(BaseModel):
    """Information about a supported exchange."""

    id: str
    name: str
    requires_secret: bool
    requires_passphrase: bool
    description: str
