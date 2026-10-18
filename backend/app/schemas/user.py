"""User schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None


class UserCreate(UserBase):
    """Schema for creating a user (admin only)."""

    password: str = Field(..., min_length=10)
    role: UserRole = UserRole.USER

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        # Un compte créé depuis l'administration passait par une règle plus
        # faible que tous les autres chemins — huit caractères, aucune
        # contrainte de composition — ce qui en faisait la porte la plus basse
        # de la maison.
        from app.schemas.auth import _validate_password_complexity

        return _validate_password_complexity(v)


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = Field(None, min_length=10)
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str | None) -> str | None:
        from app.schemas.auth import _validate_password_complexity

        return _validate_password_complexity(v) if v is not None else v


class UserResponse(UserBase):
    """Schema for user response."""

    id: UUID
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    """Schema for user in database (includes password hash)."""

    password_hash: str
    mfa_secret: str | None = None
