"""API dependencies."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import compute_token_fingerprint, decode_token
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

security = HTTPBearer()


security_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token (header or cookie)."""
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback: read from httpOnly cookie
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token fingerprint (user-agent binding)
    token_fp = payload.get("fp")
    if token_fp:
        user_agent = request.headers.get("user-agent", "")
        current_fp = compute_token_fingerprint(user_agent)
        if token_fp != current_fp:
            logger.warning(
                "Token fingerprint mismatch for user %s (IP: %s)",
                payload.get("sub"),
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token binding validation failed",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user."""
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user if they are an admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user if authenticated, None otherwise.

    Unlike get_current_user, this does not raise exceptions for invalid tokens.
    Returns None if no token, invalid token, or user not found.
    """
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    try:
        payload = decode_token(token)

        if not payload:
            return None

        if payload.get("type") != "access":
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        return user
    except Exception:
        # Silently return None for any error (invalid token format, etc.)
        return None
