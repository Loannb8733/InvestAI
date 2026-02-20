"""Security utilities: password hashing, JWT, encryption."""

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from cryptography.fernet import Fernet, MultiFernet
from jose import JWTError, jwt

from app.core.config import settings


def compute_token_fingerprint(user_agent: str) -> str:
    """Compute a fingerprint hash from the user-agent for token binding.

    This binds the token to the client's browser, preventing stolen tokens
    from being used in a different browser.
    """
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


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
    fingerprint: Optional[str] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if fingerprint:
        to_encode["fp"] = fingerprint
    encoded: str = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded


def create_refresh_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
    fingerprint: Optional[str] = None,
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    if fingerprint:
        to_encode["fp"] = fingerprint
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
def _build_fernet() -> Optional[MultiFernet]:
    """Build MultiFernet instance with key rotation support.

    Uses FERNET_KEY as the primary key and FERNET_OLD_KEYS (comma-separated)
    as fallback keys for decrypting data encrypted with previous keys.
    """
    if not settings.FERNET_KEY:
        return None
    current_key = settings.FERNET_KEY
    keys = [Fernet(current_key.encode())]
    old_keys = getattr(settings, "FERNET_OLD_KEYS", "") or ""
    if old_keys:
        for k in old_keys.split(","):
            k = k.strip()
            if k:
                keys.append(Fernet(k.encode()))
    return MultiFernet(keys)


def get_fernet() -> Optional[MultiFernet]:
    """Get MultiFernet instance for encryption with key rotation support."""
    return _build_fernet()


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
