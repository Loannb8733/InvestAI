"""Notification endpoints."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.notification import NotificationPriority, NotificationType
from app.models.user import User
from app.services.notification_service import notification_service

router = APIRouter()


class NotificationResponse(BaseModel):
    """Notification response schema."""

    id: UUID
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority
    is_read: bool
    reference_type: str | None
    reference_id: UUID | None
    created_at: str

    class Config:
        from_attributes = True


class NotificationCountResponse(BaseModel):
    """Notification count response."""

    unread_count: int


class MarkReadRequest(BaseModel):
    """Request to mark notification as read."""

    notification_id: UUID


@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[NotificationResponse]:
    """List notifications for current user."""
    notifications = await notification_service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=min(limit, 100),  # Cap at 100
        offset=offset,
    )
    return [
        NotificationResponse(
            id=n.id,
            type=n.type,
            title=n.title,
            message=n.message,
            priority=n.priority,
            is_read=n.is_read,
            reference_type=n.reference_type,
            reference_id=n.reference_id,
            created_at=n.created_at.isoformat(),
        )
        for n in notifications
    ]


@router.get("/count", response_model=NotificationCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationCountResponse:
    """Get count of unread notifications."""
    count = await notification_service.get_unread_count(db, current_user.id)
    return NotificationCountResponse(unread_count=count)


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    success = await notification_service.mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"message": "Notification marked as read"}


@router.post("/read-all")
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    count = await notification_service.mark_all_as_read(db, current_user.id)
    return {"message": f"{count} notifications marked as read"}
