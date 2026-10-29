import logging
from uuid import UUID

from app.core.config import settings
from app.core.errors import NotFoundError
from app.domains.notifications.mail import send_email
from app.domains.notifications.models import Notification, NotificationPriority, NotificationType
from app.domains.notifications.repository import NotificationRepository
from app.domains.notifications.schemas import MessageResponse, NotificationCountResponse, NotificationResponse

logger = logging.getLogger(__name__)

NOTIFICATION_NOT_FOUND = "Notification non trouvée"
MAX_PAGE_SIZE = 100


def _to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        priority=notification.priority,
        is_read=notification.is_read,
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        created_at=notification.created_at.isoformat(),
    )


class NotificationService:
    """Notifications d'un utilisateur : création, courriel associé et lecture."""

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    async def send(
        self,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        send_email: bool = True,
        send_in_app: bool = True,
    ) -> Notification | None:
        """Crée la notification dans l'application et l'envoie par courriel quand SMTP est configuré."""
        notification = None
        if send_in_app:
            notification = await self._repository.add(
                Notification(
                    user_id=user_id,
                    type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    is_read=False,
                )
            )
            logger.info("Created in-app notification for user %s: %s", user_id, title)
        if send_email and settings.email_enabled:
            await self._email(user_id, title, message, priority)
        return notification

    async def _email(self, user_id: UUID, title: str, message: str, priority: NotificationPriority) -> None:
        recipient = await self._repository.recipient(user_id)
        if recipient and recipient.email:
            name = f"{recipient.first_name or ''} {recipient.last_name or ''}".strip() or recipient.email
            await send_email(recipient.email, name, title, message, priority)

    async def send_alert(
        self,
        user_id: UUID,
        alert_name: str,
        message: str,
        alert_id: UUID,
        notify_email: bool = True,
        notify_in_app: bool = True,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> Notification | None:
        """Notifie le déclenchement d'une alerte, titrée « Alerte: <nom> »."""
        return await self.send(
            user_id,
            NotificationType.ALERT_TRIGGERED,
            f"Alerte: {alert_name}",
            message,
            priority,
            reference_type="alert",
            reference_id=alert_id,
            send_email=notify_email,
            send_in_app=notify_in_app,
        )

    async def find(self, user_id: UUID, unread_only: bool, limit: int, offset: int) -> list[NotificationResponse]:
        """Notifications de l'utilisateur, des plus récentes aux plus anciennes, 100 au plus par page."""
        found = await self._repository.find(user_id, unread_only, min(limit, MAX_PAGE_SIZE), offset)
        return [_to_response(notification) for notification in found]

    async def unread_count(self, user_id: UUID) -> NotificationCountResponse:
        return NotificationCountResponse(unread_count=await self._repository.unread_count(user_id))

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> MessageResponse:
        """Marque lue une notification de l'utilisateur ; 404 si elle ne lui appartient pas."""
        if not await self._repository.mark_read(notification_id, user_id):
            raise NotFoundError(NOTIFICATION_NOT_FOUND)
        return MessageResponse(message="Notification marked as read")

    async def mark_all_read(self, user_id: UUID) -> MessageResponse:
        count = await self._repository.mark_all_read(user_id)
        return MessageResponse(message=f"{count} notifications marked as read")
