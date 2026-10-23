from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domains.identity.models import UserRole
from app.domains.identity.passwords import MIN_LENGTH, check_password_strength

TMI_BRACKETS = (0.0, 0.11, 0.30, 0.41, 0.45)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_LENGTH)
    first_name: str | None = None
    last_name: str | None = None

    _strength = field_validator("password")(check_password_strength)


class RegisterResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(None, min_length=6, max_length=8)
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class MfaSetupResponse(BaseModel):
    secret: str
    qr_code: str
    backup_codes: list[str]


class MfaCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=MIN_LENGTH)

    _strength = field_validator("new_password")(check_password_strength)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=MIN_LENGTH)

    _strength = field_validator("new_password")(check_password_strength)


class ProfileResponse(BaseModel):
    id: str
    email: str
    role: str
    first_name: str | None
    last_name: str | None
    preferred_currency: str
    mfa_enabled: bool
    telegram_chat_id: str | None = None
    telegram_enabled: bool = False
    tmi_rate: float | None = None
    risk_profile: str | None = None
    monthly_dca_eur: float | None = None
    created_at: str


class ProfileUpdate(BaseModel):
    """Champs modifiables par l'utilisateur lui-même ; ``null`` efface une valeur du profil investisseur."""

    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    preferred_currency: str | None = Field(None, pattern=r"^(EUR|USD|CHF|GBP)$")
    telegram_chat_id: str | None = Field(None, max_length=100, pattern=r"^-?\d+$")
    telegram_enabled: bool | None = None
    tmi_rate: float | None = None
    risk_profile: Literal["conservative", "moderate", "aggressive"] | None = None
    monthly_dca_eur: float | None = Field(None, ge=0, le=99_999_999.99)

    @field_validator("tmi_rate")
    @classmethod
    def _bracket(cls, value: float | None) -> float | None:
        if value is not None and not any(abs(value - bracket) < 1e-9 for bracket in TMI_BRACKETS):
            raise ValueError("TMI invalide : valeurs autorisées 0, 0.11, 0.30, 0.41, 0.45")
        return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_LENGTH)
    role: UserRole = UserRole.USER
    first_name: str | None = None
    last_name: str | None = None

    _strength = field_validator("password")(check_password_strength)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = Field(None, min_length=MIN_LENGTH)
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str | None) -> str | None:
        return check_password_strength(value) if value is not None else value


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
