"""Notification service for email and in-app notifications."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via email and in-app."""

    async def send_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        reference_type: Optional[str] = None,
        reference_id: Optional[UUID] = None,
        send_email: bool = True,
        send_in_app: bool = True,
    ) -> Optional[Notification]:
        """Send a notification to a user."""
        notification = None

        # Create in-app notification
        if send_in_app:
            notification = await self._create_in_app_notification(
                db=db,
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                reference_type=reference_type,
                reference_id=reference_id,
            )

        # Send email notification
        if send_email and settings.email_enabled:
            user = await self._get_user(db, user_id)
            if user and user.email:
                await self._send_email(
                    to_email=user.email,
                    to_name=f"{user.first_name or ''} {user.last_name or ''}".strip()
                    or user.email,
                    subject=title,
                    body=message,
                    priority=priority,
                )

        return notification

    async def send_alert_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        alert_name: str,
        symbol: str,
        message: str,
        alert_id: UUID,
        notify_email: bool = True,
        notify_in_app: bool = True,
    ) -> Optional[Notification]:
        """Send an alert triggered notification."""
        title = f"Alerte: {alert_name}"

        return await self.send_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.ALERT_TRIGGERED,
            title=title,
            message=message,
            priority=NotificationPriority.HIGH,
            reference_type="alert",
            reference_id=alert_id,
            send_email=notify_email,
            send_in_app=notify_in_app,
        )

    async def get_user_notifications(
        self,
        db: AsyncSession,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        """Get notifications for a user."""
        query = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            query = query.where(Notification.is_read == False)

        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def mark_as_read(
        self,
        db: AsyncSession,
        notification_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Mark a notification as read."""
        result = await db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .values(is_read=True)
        )
        await db.commit()
        return result.rowcount > 0

    async def mark_all_as_read(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        """Mark all notifications as read for a user."""
        result = await db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
            .values(is_read=True)
        )
        await db.commit()
        return result.rowcount

    async def get_unread_count(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        """Get count of unread notifications."""
        from sqlalchemy import func

        result = await db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        )
        return result.scalar() or 0

    async def _create_in_app_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority,
        reference_type: Optional[str] = None,
        reference_id: Optional[UUID] = None,
    ) -> Notification:
        """Create an in-app notification."""
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            priority=priority,
            reference_type=reference_type,
            reference_id=reference_id,
            is_read=False,
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        logger.info(
            f"Created in-app notification for user {user_id}: {title}",
            extra={"user_id": str(user_id), "notification_type": notification_type.value},
        )

        return notification

    async def _get_user(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """Send an email notification."""
        if not settings.email_enabled:
            logger.warning("Email not configured, skipping email notification")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{settings.APP_NAME}] {subject}"
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = f"{to_name} <{to_email}>"

            # Set priority headers
            if priority == NotificationPriority.URGENT:
                msg["X-Priority"] = "1"
                msg["X-MSMail-Priority"] = "High"
            elif priority == NotificationPriority.HIGH:
                msg["X-Priority"] = "2"
                msg["X-MSMail-Priority"] = "High"

            # Plain text version
            text_content = f"""
{subject}

{body}

---
Ceci est un message automatique de {settings.APP_NAME}.
Ne répondez pas à cet email.
"""

            # HTML version
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1a1a2e; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{settings.APP_NAME}</h1>
        </div>
        <div class="content">
            <h2>{subject}</h2>
            <p>{body}</p>
        </div>
        <div class="footer">
            <p>Ceci est un message automatique de {settings.APP_NAME}.<br>Ne répondez pas à cet email.</p>
        </div>
    </div>
</body>
</html>
"""

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # Send email
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False


# Singleton instance
notification_service = NotificationService()
