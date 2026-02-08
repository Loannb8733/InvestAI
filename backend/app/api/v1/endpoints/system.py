"""System administration endpoints."""

from typing import Optional
from pydantic import BaseModel, EmailStr

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_active_user
from app.models.user import User, UserRole
from app.services.email_service import email_service

router = APIRouter()


class EmailTestRequest(BaseModel):
    """Request to send a test email."""
    to_email: Optional[EmailStr] = None


class EmailTestResponse(BaseModel):
    """Response from email test."""
    success: bool
    message: str
    email_configured: bool
    smtp_host: Optional[str] = None


class SystemStatusResponse(BaseModel):
    """System status response."""
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_from: str
    celery_tasks: list


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    current_user: User = Depends(require_admin),
):
    """Get system status (admin only)."""
    return SystemStatusResponse(
        email_enabled=settings.email_enabled,
        smtp_host=settings.SMTP_HOST or "(not configured)",
        smtp_port=settings.SMTP_PORT,
        smtp_from=settings.SMTP_FROM_EMAIL,
        celery_tasks=[
            "update-crypto-prices (5 min)",
            "update-stock-prices (5 min)",
            "sync-exchanges (1 hour)",
            "check-alerts (5 min)",
            "create-daily-snapshots (00:00 UTC)",
            "send-weekly-reports (Sunday 18:00 UTC)",
            "send-monthly-reports (1st of month 08:00 UTC)",
            "send-daily-digest (07:00 UTC)",
            "run-weekly-cleanup (Monday 03:00 UTC)",
        ],
    )


@router.post("/test-email", response_model=EmailTestResponse)
async def test_email(
    request: EmailTestRequest,
    current_user: User = Depends(require_admin),
):
    """
    Send a test email to verify SMTP configuration (admin only).
    If no email specified, sends to the admin's email.
    """
    if not email_service.is_configured:
        return EmailTestResponse(
            success=False,
            message="Email is not configured. Check SMTP settings in .env",
            email_configured=False,
        )

    to_email = request.to_email or current_user.email

    content = f"""
    <h2>Test Email - InvestAI</h2>
    <p>Ceci est un email de test pour verifier la configuration SMTP.</p>
    <div class="alert-box alert-success">
        <strong>Configuration valide</strong><br>
        Si vous recevez cet email, la configuration SMTP fonctionne correctement.
    </div>
    <p>Details de configuration:</p>
    <ul>
        <li>Host: {settings.SMTP_HOST}</li>
        <li>Port: {settings.SMTP_PORT}</li>
        <li>TLS: {'Oui' if settings.SMTP_TLS else 'Non'}</li>
        <li>From: {settings.SMTP_FROM_EMAIL}</li>
    </ul>
    """

    html = email_service._get_base_template(content, "Test Email")

    success = await email_service.send_email(
        to_email=to_email,
        subject="[InvestAI] Test de configuration email",
        html_content=html,
    )

    if success:
        return EmailTestResponse(
            success=True,
            message=f"Email de test envoye avec succes a {to_email}",
            email_configured=True,
            smtp_host=settings.SMTP_HOST,
        )
    else:
        return EmailTestResponse(
            success=False,
            message="Echec de l'envoi. Verifiez les logs pour plus de details.",
            email_configured=True,
            smtp_host=settings.SMTP_HOST,
        )


@router.post("/trigger-weekly-report")
async def trigger_weekly_report(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger weekly report for current user (admin only)."""
    from app.services.metrics_service import metrics_service
    from app.services.snapshot_service import snapshot_service

    if not email_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not configured",
        )

    try:
        metrics = await metrics_service.get_user_dashboard_metrics(db, str(current_user.id))

        if metrics["total_value"] == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No portfolio value to report",
            )

        history = await snapshot_service.get_historical_values(
            db, str(current_user.id), days=7
        )

        week_start_value = history[0]["value"] if history else metrics["total_value"]
        week_change = metrics["total_value"] - week_start_value
        week_change_pct = (week_change / week_start_value * 100) if week_start_value > 0 else 0

        success = await email_service.send_weekly_report(
            to_email=current_user.email,
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email.split("@")[0],
            total_value=metrics["total_value"],
            total_invested=metrics["total_invested"],
            week_change=week_change,
            week_change_pct=week_change_pct,
            top_performers=[],
            worst_performers=[],
        )

        if success:
            return {"message": f"Weekly report sent to {current_user.email}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send email",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
