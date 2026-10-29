import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.domains.notifications.models import NotificationPriority

logger = logging.getLogger(__name__)

PRIORITY_HEADERS = {NotificationPriority.URGENT: "1", NotificationPriority.HIGH: "2"}


def _deliver(to_email: str, message: str) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_TLS:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, message)


def _text(subject: str, body: str) -> str:
    return f"""
{subject}

{body}

---
Ceci est un message automatique de {settings.APP_NAME}.
Ne répondez pas à cet email.
"""


def _html(subject: str, body: str) -> str:
    return f"""
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
"""  # noqa: E501


def _message(to_email: str, to_name: str, subject: str, body: str, priority: NotificationPriority) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = f"[{settings.APP_NAME}] {subject}"
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = f"{to_name} <{to_email}>"
    if priority in PRIORITY_HEADERS:
        message["X-Priority"] = PRIORITY_HEADERS[priority]
        message["X-MSMail-Priority"] = "High"
    message.attach(MIMEText(_text(subject, body), "plain", "utf-8"))
    message.attach(MIMEText(_html(subject, body), "html", "utf-8"))
    return message


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
) -> bool:
    """Envoie un courriel de notification ; rend False sans SMTP configuré ou si l'envoi échoue."""
    if not settings.email_enabled:
        logger.warning("Email not configured, skipping email notification")
        return False
    try:
        message = _message(to_email, to_name, subject, body, priority)
        await asyncio.to_thread(_deliver, to_email, message.as_string())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False
    logger.info("Email sent to %s: %s", to_email, subject)
    return True
