"""API Key model."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


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
    last_sync_at = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
