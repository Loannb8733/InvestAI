"""Authentication endpoints."""

import base64
import secrets
from datetime import datetime, timedelta
from io import BytesIO

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter, RATE_LIMITS
from app.core.security import (
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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

router = APIRouter()


class RegisterResponse(BaseModel):
    """Response for registration."""
    message: str
    email_verification_required: bool = True


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["auth_register"])
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new user. Sends verification email."""
    from app.core.config import settings
    from app.services.email_service import email_service

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == register_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà",
        )

    # Generate verification token
    verification_token = secrets.token_urlsafe(48)
    verification_expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()

    # Create new user (inactive until email verified)
    user = User(
        email=register_data.email,
        password_hash=hash_password(register_data.password),
        first_name=register_data.first_name,
        last_name=register_data.last_name,
        is_active=False,  # Inactive until email verified
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_expires=verification_expires,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Send verification email
    try:
        frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
        verify_url = f"{frontend_url}/verify-email?token={verification_token}"

        content = f"""
        <h2>Bienvenue sur InvestAI !</h2>
        <p>Merci de vous être inscrit. Pour activer votre compte, veuillez confirmer votre adresse email.</p>
        <div style="text-align: center; margin: 24px 0;">
            <a href="{verify_url}" class="button">Confirmer mon email</a>
        </div>
        <p>Ce lien est valable <strong>24 heures</strong>.</p>
        <p>Si vous n'avez pas créé de compte sur InvestAI, ignorez simplement cet email.</p>
        """

        html = email_service._get_base_template(content, "Confirmez votre email")
        await email_service.send_email(
            to_email=user.email,
            subject="[InvestAI] Confirmez votre adresse email",
            html_content=html,
        )
    except Exception as e:
        # Log but don't fail registration
        import logging
        logging.getLogger(__name__).warning(f"Failed to send verification email: {e}")

    return RegisterResponse(
        message="Compte créé avec succès. Vérifiez votre email pour activer votre compte.",
        email_verification_required=True,
    )


class VerifyEmailRequest(BaseModel):
    """Request to verify email."""
    token: str


@router.post("/verify-email", response_model=Token)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Verify email address and activate account."""
    result = await db.execute(
        select(User).where(User.email_verification_token == data.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lien de vérification invalide ou expiré.",
        )

    # Check expiration
    if user.email_verification_expires:
        try:
            expires = datetime.fromisoformat(user.email_verification_expires)
            if datetime.utcnow() > expires:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lien de vérification expiré. Veuillez vous réinscrire.",
                )
        except ValueError:
            pass

    # Activate user
    user.is_active = True
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires = None
    await db.commit()

    # Generate tokens for automatic login
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/resend-verification")
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
        user.email_verification_expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
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
        except Exception:
            pass

    # Always return success to prevent email enumeration
    return {"message": "Si un compte non vérifié existe avec cette adresse, un email a été envoyé."}


@router.post("/login", response_model=Token)
@limiter.limit(RATE_LIMITS["auth_login"])
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate user and return tokens."""
    # Find user by email
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        # Check if it's because email is not verified
        if hasattr(user, 'email_verified') and not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Veuillez vérifier votre email avant de vous connecter.",
            )
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

        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(login_data.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    # Generate tokens
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
@limiter.limit(RATE_LIMITS["auth_refresh"])
async def refresh_token(
    request: Request,
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Refresh access token using refresh token."""
    payload = decode_token(refresh_data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Generate new tokens
    access_token = create_access_token(subject=str(user.id))
    new_refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


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

    # Store secret (not enabled yet)
    current_user.mfa_secret = secret
    await db.commit()

    return MFASetupResponse(
        secret=secret,
        qr_code=f"data:image/png;base64,{qr_base64}",
    )


@router.post("/mfa/verify")
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


@router.post("/mfa/disable")
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
    await db.commit()

    return {"message": "MFA disabled successfully"}


@router.get("/me")
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
        "created_at": current_user.created_at.isoformat(),
    }


@router.patch("/me")
async def update_profile(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile (first_name, last_name, preferred_currency)."""
    allowed_fields = {"first_name", "last_name", "preferred_currency"}
    # Validate currency
    if "preferred_currency" in data:
        valid_currencies = {"EUR", "USD", "CHF", "GBP"}
        if data["preferred_currency"] not in valid_currencies:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Currency must be one of: {', '.join(valid_currencies)}",
            )
    for field, value in data.items():
        if field in allowed_fields:
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
        "created_at": current_user.created_at.isoformat(),
    }


@router.post("/change-password")
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


@router.post("/forgot-password")
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
        user.password_reset_expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        await db.commit()

        # Send email
        try:
            from app.core.config import settings
            from app.services.notification_service import NotificationService

            frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:3000"
            reset_url = f"{frontend_url}/reset-password?token={token}"

            body = (
                f'Vous avez demandé la réinitialisation de votre mot de passe.<br><br>'
                f'<a href="{reset_url}" style="display:inline-block;padding:12px 24px;'
                f'background:#6366f1;color:#fff;border-radius:8px;text-decoration:none;'
                f'font-weight:bold;">Réinitialiser mon mot de passe</a><br><br>'
                f'Ce lien est valable <strong>1 heure</strong>.<br>'
                f"Si vous n'avez pas fait cette demande, ignorez cet email."
            )

            ns = NotificationService()
            await ns._send_email(
                to_email=user.email,
                to_name=user.first_name or "",
                subject="Réinitialisation de votre mot de passe",
                body=body,
            )
        except Exception:
            # Don't fail the request if email sending fails
            pass

    # Always return success to prevent email enumeration
    return {"message": "Si un compte existe avec cette adresse, un email de réinitialisation a été envoyé."}


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a token from the forgot-password email."""
    result = await db.execute(
        select(User).where(User.password_reset_token == data.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lien de réinitialisation invalide ou expiré.",
        )

    # Check expiration
    if user.password_reset_expires:
        try:
            expires = datetime.fromisoformat(user.password_reset_expires)
            if datetime.utcnow() > expires:
                user.password_reset_token = None
                user.password_reset_expires = None
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lien de réinitialisation expiré. Veuillez en demander un nouveau.",
                )
        except ValueError:
            pass

    # Update password and clear token
    user.password_hash = hash_password(data.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()

    return {"message": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."}
