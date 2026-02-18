"""User model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)
    preferred_currency = Column(String(10), default="EUR", nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(255), nullable=True)
    email_verification_expires = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
