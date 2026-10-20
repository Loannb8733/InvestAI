"""System administration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.domains.identity.dependencies import get_current_user
from app.domains.identity.models import User, UserRole

router = APIRouter()


class SystemStatusResponse(BaseModel):
    """System status response."""

    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_from: str
    celery_tasks: list


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès administrateur requis",
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
