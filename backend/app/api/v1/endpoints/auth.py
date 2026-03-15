"""Authentication endpoints."""

import base64
import json
import logging
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import RATE_LIMITS, limiter
from app.core.security import (
    compute_token_fingerprint,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    RegisterRequest,
    Token,
)


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class UserProfileResponse(BaseModel):
    """User profile response."""

    id: str
    email: str
    role: str
    first_name: Optional[str]
    last_name: Optional[str]
    preferred_currency: str
    mfa_enabled: bool
    telegram_chat_id: Optional[str] = None
    telegram_enabled: bool = False
    created_at: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        import re

        if not re.search(r"[A-Z]", v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r"\d", v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


router = APIRouter()


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    refresh_max_age_days: int | None = None,
) -> None:
    """Set httpOnly auth cookies on the response."""
    from app.core.config import settings

    common = {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.COOKIE_SECURE,
        "domain": settings.COOKIE_DOMAIN,
    }
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/api",
        **common,
    )
    refresh_days = refresh_max_age_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=refresh_days * 86400,
        path="/api/v1/auth",
        **common,
    )


class RegisterResponse(BaseModel):
    """Response for registration."""

    message: str
    email_verification_required: bool = False


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["auth_register"])
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new user."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == register_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà",
        )

    # Create new user (active immediately, no email verification)
    user = User(
        email=register_data.email,
        password_hash=hash_password(register_data.password),
        first_name=register_data.first_name,
        last_name=register_data.last_name,
        is_active=True,
        email_verified=True,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return RegisterResponse(
        message="Compte créé avec succès.",
        email_verification_required=False,
    )


class VerifyEmailRequest(BaseModel):
    """Request to verify email."""

    token: str


class UserProfileUpdate(BaseModel):
    """Request to update user profile."""

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    preferred_currency: Optional[str] = Field(None, pattern=r"^(EUR|USD|CHF|GBP)$")
    telegram_chat_id: Optional[str] = Field(None, max_length=100, pattern=r"^-?\d+$")
    telegram_enabled: Optional[bool] = None


@router.post("/verify-email", response_model=Token)
async def verify_email(
    request: Request,
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Verify email address and activate account."""
    result = await db.execute(select(User).where(User.email_verification_token == data.token))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lien de vérification invalide ou expiré.",
        )

    # Check expiration
    if user.email_verification_expires:
        expires = user.email_verification_expires
        if hasattr(expires, "tzinfo") and expires.tzinfo is not None:
            expires = expires.replace(tzinfo=None)
        if datetime.utcnow() > expires:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de vérification expiré. Veuillez vous réinscrire.",
            )

    # Activate user
    user.is_active = True
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires = None
    await db.commit()

    # Generate tokens for automatic login with fingerprint
    fp = compute_token_fingerprint(request.headers.get("user-agent", ""))
    access_token = create_access_token(subject=str(user.id), fingerprint=fp)
    refresh_token = create_refresh_token(subject=str(user.id), fingerprint=fp)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    data: ForgotPasswordRequest,  # Reuses email-only schema
    db: AsyncSession = Depends(get_db),
):
    """Resend verification email."""
    from app.core.config import settings
    from app.services.email_service import email_service

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and not user.email_verified:
        # Generate new token
        verification_token = secrets.token_urlsafe(48)
        user.email_verification_token = verification_token
        user.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
        await db.commit()

        # Send verification email
        try:
            frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
            verify_url = f"{frontend_url}/verify-email?token={verification_token}"

            content = f"""
            <h2>Confirmez votre email</h2>
            <p>Vous avez demandé un nouveau lien de vérification.</p>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{verify_url}" class="button">Confirmer mon email</a>
            </div>
            <p>Ce lien est valable <strong>24 heures</strong>.</p>
            """

            html = email_service._get_base_template(content, "Confirmez votre email")
            await email_service.send_email(
                to_email=user.email,
                subject="[InvestAI] Nouveau lien de vérification",
                html_content=html,
            )
        except Exception as e:
            logger.warning(f"Failed to send verification email to {user.email}: {e}")

    # Always return success to prevent email enumeration
    return {"message": "Si un compte non vérifié existe avec cette adresse, un email a été envoyé."}


@router.post("/login", response_model=Token)
@limiter.limit(RATE_LIMITS["auth_login"])
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate user and return tokens."""
    from app.core.redis_client import _get_redis_txt

    # Find user by email
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    # Check per-account lockout BEFORE password verification to avoid
    # wasting bcrypt CPU on locked accounts and prevent timing attacks
    if user:
        try:
            r = await _get_redis_txt()
            fail_key = f"login_fail:{user.id}"
            fails = int(await r.get(fail_key) or 0)
            if fails >= 10:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Account temporarily locked. Please try again in 15 minutes.",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Redis down — fail open

    if not user or not verify_password(login_data.password, user.password_hash):
        # Track per-account failed attempts (even if user not found, use email hash)
        if user:
            try:
                r = await _get_redis_txt()
                fail_key = f"login_fail:{user.id}"
                await r.incr(fail_key)
                await r.expire(fail_key, 900)  # 15-minute window
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )

    # Check MFA if enabled
    if user.mfa_enabled:
        if not login_data.mfa_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA code required",
            )

        # Anti-replay: reject TOTP codes already used within this window
        try:
            r = await _get_redis_txt()
            used_key = f"totp_used:{user.id}:{login_data.mfa_code}"
            if await r.exists(used_key):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="MFA code already used. Wait for the next code.",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Redis down — fail open

        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(login_data.mfa_code):
            # Mark code as used to prevent replay
            try:
                r = await _get_redis_txt()
                await r.setex(f"totp_used:{user.id}:{login_data.mfa_code}", 90, "1")
            except Exception:
                pass
        elif user.mfa_backup_codes:
            # Try backup codes
            codes = json.loads(user.mfa_backup_codes)
            matched = False
            for i, hashed_code in enumerate(codes):
                if verify_password(login_data.mfa_code, hashed_code):
                    codes.pop(i)
                    user.mfa_backup_codes = json.dumps(codes)
                    matched = True
                    break
            if not matched:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid MFA code",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

        # Persist backup code consumption if one was used
        await db.commit()

    # Clear failed login counter on success
    try:
        r = await _get_redis_txt()
        await r.delete(f"login_fail:{user.id}")
    except Exception:
        pass

    # Generate tokens with fingerprint binding
    fp = compute_token_fingerprint(request.headers.get("user-agent", ""))
    access_token = create_access_token(subject=str(user.id), fingerprint=fp)

    # "Remember me" → 30-day refresh token, otherwise default (7 days)
    remember_days = 30 if login_data.remember_me else None
    refresh_delta = timedelta(days=remember_days) if remember_days else None
    refresh_tok = create_refresh_token(subject=str(user.id), fingerprint=fp, expires_delta=refresh_delta)

    # Set httpOnly cookies
    _set_auth_cookies(response, access_token, refresh_tok, refresh_max_age_days=remember_days)

    return Token(
        access_token=access_token,
        refresh_token=refresh_tok,
    )


@router.post("/refresh", response_model=Token)
@limiter.limit(RATE_LIMITS["auth_refresh"])
async def refresh_token(
    request: Request,
    response: Response,
    refresh_data: Optional[RefreshTokenRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Refresh access token using refresh token (from body or cookie)."""
    # Try body first, then cookie
    raw_token = None
    if refresh_data and refresh_data.refresh_token:
        raw_token = refresh_data.refresh_token
    else:
        raw_token = request.cookies.get("refresh_token")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    payload = decode_token(raw_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Check if this refresh token has been revoked (blocklisted on logout)
    from app.core.redis_client import _get_redis_txt

    jti = payload.get("jti")
    if jti:
        try:
            r = await _get_redis_txt()
            if await r.exists(f"token_blocklist:{jti}"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Redis down — fail open

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Verify refresh token fingerprint
    token_fp = payload.get("fp")
    if token_fp:
        user_agent = request.headers.get("user-agent", "")
        current_fp = compute_token_fingerprint(user_agent)
        if token_fp != current_fp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token binding validation failed",
            )

    # Generate new tokens with fingerprint
    fp = compute_token_fingerprint(request.headers.get("user-agent", ""))
    access_token = create_access_token(subject=str(user.id), fingerprint=fp)
    new_refresh_token = create_refresh_token(subject=str(user.id), fingerprint=fp)

    # Set httpOnly cookies
    _set_auth_cookies(response, access_token, new_refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response) -> dict:
    """Clear auth cookies and revoke refresh token."""
    # Blocklist the refresh token's jti so it can't be reused
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        try:
            payload = decode_token(raw_refresh)
            if payload and payload.get("jti"):
                from app.core.redis_client import _get_redis_txt

                r = await _get_redis_txt()
                # TTL = remaining token lifetime (exp - now), capped at 7 days
                exp = payload.get("exp", 0)
                ttl = max(1, int(exp - datetime.utcnow().timestamp()))
                ttl = min(ttl, 7 * 86400)
                await r.setex(f"token_blocklist:{payload['jti']}", ttl, "1")
        except Exception:
            pass  # Best-effort revocation; cookie deletion still provides baseline protection

    response.delete_cookie("access_token", path="/api")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return {"message": "Déconnexion réussie"}


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    """Setup MFA for current user."""
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled",
        )

    # Generate secret
    secret = pyotp.random_base32()

    # Generate QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="InvestAI",
    )

    # Create QR code image
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    # Generate backup codes
    plain_codes = [secrets.token_hex(4) for _ in range(10)]
    hashed_codes = [hash_password(code) for code in plain_codes]

    # Store secret and backup codes (not enabled yet)
    current_user.mfa_secret = secret
    current_user.mfa_backup_codes = json.dumps(hashed_codes)
    await db.commit()

    return MFASetupResponse(
        secret=secret,
        qr_code=f"data:image/png;base64,{qr_base64}",
        backup_codes=plain_codes,
    )


@router.post("/mfa/verify", response_model=MessageResponse)
async def verify_mfa(
    request: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify and enable MFA for current user."""
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup not initiated",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    current_user.mfa_enabled = True
    await db.commit()

    return {"message": "MFA enabled successfully"}


@router.post("/mfa/disable", response_model=MessageResponse)
async def disable_mfa(
    request: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable MFA for current user."""
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    await db.commit()

    return {"message": "MFA disabled successfully"}


@router.get("/mfa/backup-codes-count")
async def get_backup_codes_count(
    current_user: User = Depends(get_current_user),
):
    """Get the number of remaining MFA backup codes."""
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )
    codes = json.loads(current_user.mfa_backup_codes or "[]")
    return {"remaining_codes": len(codes)}


@router.post("/mfa/regenerate-backup-codes")
async def regenerate_backup_codes(
    request: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate MFA backup codes. Requires a valid TOTP code."""
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    # Generate new codes
    plain_codes = [secrets.token_hex(4) for _ in range(10)]
    hashed_codes = [hash_password(code) for code in plain_codes]
    current_user.mfa_backup_codes = json.dumps(hashed_codes)
    await db.commit()

    return {"backup_codes": plain_codes, "message": "New backup codes generated"}


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current user information."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role.value,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "preferred_currency": getattr(current_user, "preferred_currency", "EUR"),
        "mfa_enabled": current_user.mfa_enabled,
        "telegram_chat_id": current_user.telegram_chat_id,
        "telegram_enabled": getattr(current_user, "telegram_enabled", False),
        "created_at": current_user.created_at.isoformat(),
    }


@router.patch("/me", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile (first_name, last_name, preferred_currency)."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role.value,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "preferred_currency": getattr(current_user, "preferred_currency", "EUR"),
        "mfa_enabled": current_user.mfa_enabled,
        "telegram_chat_id": current_user.telegram_chat_id,
        "telegram_enabled": getattr(current_user, "telegram_enabled", False),
        "created_at": current_user.created_at.isoformat(),
    }


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password."""
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect",
        )

    current_user.password_hash = hash_password(password_data.new_password)
    await db.commit()

    return {"message": "Mot de passe modifié avec succès"}


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset link. Always returns success to avoid email enumeration."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # Generate secure token
        token = secrets.token_urlsafe(48)
        user.password_reset_token = token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()

        # Send email
        try:
            from app.core.config import settings
            from app.services.notification_service import NotificationService

            frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
            reset_url = f"{frontend_url}/reset-password?token={token}"

            body = (
                f"Vous avez demandé la réinitialisation de votre mot de passe.<br><br>"
                f'<a href="{reset_url}" style="display:inline-block;padding:12px 24px;'
                f"background:#6366f1;color:#fff;border-radius:8px;text-decoration:none;"
                f'font-weight:bold;">Réinitialiser mon mot de passe</a><br><br>'
                f"Ce lien est valable <strong>1 heure</strong>.<br>"
                f"Si vous n'avez pas fait cette demande, ignorez cet email."
            )

            ns = NotificationService()
            await ns._send_email(
                to_email=user.email,
                to_name=user.first_name or "",
                subject="Réinitialisation de votre mot de passe",
                body=body,
            )
        except Exception as e:
            logger.warning(f"Failed to send password reset email: {e}")

    # Always return success to prevent email enumeration
    return {"message": "Si un compte existe avec cette adresse, un email de réinitialisation a été envoyé."}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a token from the forgot-password email."""
    result = await db.execute(select(User).where(User.password_reset_token == data.token))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lien de réinitialisation invalide ou expiré.",
        )

    # Check expiration
    if user.password_reset_expires:
        expires = user.password_reset_expires
        if hasattr(expires, "tzinfo") and expires.tzinfo is not None:
            expires = expires.replace(tzinfo=None)
        if datetime.utcnow() > expires:
            user.password_reset_token = None
            user.password_reset_expires = None
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lien de réinitialisation expiré. Veuillez en demander un nouveau.",
            )

    # Update password and clear token
    user.password_hash = hash_password(data.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()

    return {"message": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."}
