import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base

MAX_ERROR_LENGTH = 500
FAILURES_BEFORE_DISABLE = 5


class APIKeyStatus(enum.StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class APIKey(Base):
    """Clé d'API d'exchange ; les secrets sont chiffrés (Fernet) et jamais rendus."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_secret_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[APIKeyStatus] = mapped_column(
        Enum(APIKeyStatus, name="apikeystatus", values_callable=lambda values: [v.value for v in values]),
        nullable=False,
        server_default="active",
    )
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def _failed(self, error: str, status: APIKeyStatus) -> None:
        self.status = status
        self.error_count = (self.error_count or 0) + 1
        self.last_error = str(error)[:MAX_ERROR_LENGTH]

    def mark_auth_failure(self, error_msg: str) -> None:
        """Identifiants refusés (401/403) : la clé est désactivée."""
        self._failed(error_msg, APIKeyStatus.EXPIRED)
        self.is_active = False

    def mark_rate_limited(self, error_msg: str) -> None:
        """Quota atteint (429) : la clé reste active pour le prochain passage."""
        self._failed(error_msg, APIKeyStatus.RATE_LIMITED)

    def mark_error(self, error_msg: str) -> None:
        """Autre erreur ; la clé est désactivée après cinq échecs consécutifs."""
        self._failed(error_msg, APIKeyStatus.ERROR)
        if self.error_count >= FAILURES_BEFORE_DISABLE:
            self.is_active = False

    def mark_success(self) -> None:
        self.status = APIKeyStatus.ACTIVE
        self.error_count = 0
        self.last_error = None


class ColdWalletAddress(Base):
    """Nom donné à une adresse de retrait : la synchronisation y range le transfert entrant miroir."""

    __tablename__ = "cold_wallet_addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_cold_wallet_user_address"),)
