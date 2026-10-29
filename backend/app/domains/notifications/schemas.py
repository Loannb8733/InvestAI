from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.notifications.models import NotificationPriority, NotificationType


class MessageResponse(BaseModel):
    message: str


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority
    is_read: bool
    reference_type: str | None
    reference_id: UUID | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class NotificationCountResponse(BaseModel):
    unread_count: int
