"""Authentication schemas."""

import re
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


def _validate_password_complexity(password: str) -> str:
    """Enforce password complexity: min 10 chars, 1 uppercase, 1 digit."""
    if len(password) < 10:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Le mot de passe doit contenir au moins une majuscule")
    if not re.search(r"\d", password):
        raise ValueError("Le mot de passe doit contenir au moins un chiffre")
    return password


class RegisterRequest(BaseModel):
    """Schema for registration request."""

    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str
    mfa_code: Optional[str] = Field(None, min_length=6, max_length=8)
    remember_me: bool = False


class Token(BaseModel):
    """Schema for token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: str
    exp: int
    type: str


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class MFASetupResponse(BaseModel):
    """Schema for MFA setup response."""

    secret: str
    qr_code: str  # Base64 encoded QR code image
    backup_codes: List[str]


class MFAVerifyRequest(BaseModel):
    """Schema for MFA verification request."""

    code: str = Field(..., min_length=6, max_length=6)


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""

    current_password: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""

    token: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password_complexity(v)
