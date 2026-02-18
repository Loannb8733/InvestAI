"""Application configuration."""

import os
import secrets
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "InvestAI"
    APP_ENV: str = "development"
    DEBUG: bool = False  # Secure default: disabled
    API_V1_PREFIX: str = "/api/v1"

    # Security - No default values for sensitive keys (must be in .env)
    SECRET_KEY: str  # Required - no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # Encryption for API keys - Required for production
    FERNET_KEY: str  # Required - no default

    # Database - Credentials must come from environment
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "investai"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "investai"

    # Database pool configuration
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_RECYCLE: int = 3600

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure SECRET_KEY is secure."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if v in ["your-secret-key-change-in-production", "changeme", "secret"]:
            raise ValueError("SECRET_KEY must not be a default/weak value")
        return v

    @field_validator("FERNET_KEY")
    @classmethod
    def validate_fernet_key(cls, v: str) -> str:
        """Ensure FERNET_KEY is valid."""
        if not v or len(v) < 32:
            raise ValueError("FERNET_KEY must be a valid Fernet key (44 characters base64)")
        return v

    @property
    def DATABASE_URL(self) -> str:
        """Build async database URL. Uses DATABASE_URL env var (Railway) if set."""
        external = os.environ.get("DATABASE_URL", "")
        if external:
            return external.replace("postgresql://", "postgresql+asyncpg://")
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Build sync database URL for Alembic."""
        external = os.environ.get("DATABASE_URL", "")
        if external:
            return external.replace("postgresql+asyncpg://", "postgresql://")
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        """Build Redis URL. Uses REDIS_URL env var (Railway) if set."""
        external = os.environ.get("REDIS_URL", "")
        if external:
            return external
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # CORS - Restricted methods and headers
    # Override with comma-separated env var: CORS_ORIGINS=https://mysite.com,https://www.mysite.com
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    CORS_ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOWED_HEADERS: List[str] = [
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ]

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@investai.local"
    SMTP_FROM_NAME: str = "InvestAI"
    SMTP_TLS: bool = True

    @property
    def email_enabled(self) -> bool:
        """Check if email is configured."""
        return bool(self.SMTP_HOST and self.SMTP_USER)

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production" and not self.DEBUG

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
