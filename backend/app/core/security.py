"""Security utilities: password hashing, JWT, encryption."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed: str = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    result: bool = bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    return result


# JWT tokens
def create_access_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    encoded: str = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded


def create_refresh_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    encoded: str = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    try:
        payload: Dict[str, Any] = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode an access token. Alias for decode_token used by Sentry middleware."""
    return decode_token(token)


# Fernet encryption for API keys
def get_fernet() -> Optional[Fernet]:
    """Get Fernet instance for encryption."""
    if not settings.FERNET_KEY:
        return None
    return Fernet(settings.FERNET_KEY.encode())


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key using Fernet."""
    fernet = get_fernet()
    if not fernet:
        raise ValueError("FERNET_KEY not configured")
    encrypted: str = fernet.encrypt(api_key.encode()).decode()
    return encrypted


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key using Fernet."""
    fernet = get_fernet()
    if not fernet:
        raise ValueError("FERNET_KEY not configured")
    decrypted: str = fernet.decrypt(encrypted_key.encode()).decode()
    return decrypted
