"""API Key model."""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class APIKeyStatus(str, enum.Enum):
    """Status of an exchange API key."""

    ACTIVE = "active"
    EXPIRED = "expired"  # 401/403 — credentials invalid or revoked
    RATE_LIMITED = "rate_limited"  # 429 — temporary, will retry
    ERROR = "error"  # Other persistent errors


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exchange = Column(String(50), nullable=False)
    label = Column(String(100), nullable=True)
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_secret_key = Column(Text, nullable=True)
    encrypted_passphrase = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(
        Enum(APIKeyStatus, name="apikeystatus", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=False,
        server_default="active",
    )
    error_count = Column(Integer, nullable=False, server_default="0")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def mark_auth_failure(self, error_msg: str) -> None:
        """Mark key as expired (401/403). Auto-disables."""
        self.status = APIKeyStatus.EXPIRED
        self.is_active = False
        self.error_count = (self.error_count or 0) + 1
        self.last_error = str(error_msg)[:500]

    def mark_rate_limited(self, error_msg: str) -> None:
        """Mark as rate-limited (429). Stays active for next retry."""
        self.status = APIKeyStatus.RATE_LIMITED
        self.error_count = (self.error_count or 0) + 1
        self.last_error = str(error_msg)[:500]

    def mark_error(self, error_msg: str) -> None:
        """Mark generic error. Auto-disables after 5 consecutive failures."""
        self.error_count = (self.error_count or 0) + 1
        self.last_error = str(error_msg)[:500]
        if self.error_count >= 5:
            self.status = APIKeyStatus.ERROR
            self.is_active = False
        else:
            self.status = APIKeyStatus.ERROR

    def mark_success(self) -> None:
        """Reset error state after a successful sync."""
        self.status = APIKeyStatus.ACTIVE
        self.error_count = 0
        self.last_error = None
