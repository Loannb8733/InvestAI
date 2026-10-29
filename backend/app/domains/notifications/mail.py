import asyncio
import logging
import re
import smtplib
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape, unescape

from app.core.config import settings
from app.domains.notifications.models import NotificationPriority
from app.domains.notifications.template import wrap

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 30
PRIORITY_HEADERS = {NotificationPriority.URGENT: "1", NotificationPriority.HIGH: "2"}
LINK = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
LINE_BREAK = re.compile(r"<br\s*/?>")
TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes


def _deliver(to_email: str, raw: str) -> None:
    context = ssl.create_default_context()
    server = (
        smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        if settings.SMTP_TLS
        else smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    )
    with server:
        if settings.SMTP_TLS:
            server.starttls(context=context)
        if settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, raw)


def _attachment(attachment: Attachment) -> MIMEBase:
    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment.content)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={attachment.filename}")
    return part


def _message(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    text: str | None,
    priority: NotificationPriority,
    attachments: Sequence[Attachment],
) -> MIMEMultipart:
    message = body = MIMEMultipart("alternative")
    if text is not None:
        body.attach(MIMEText(text, "plain", "utf-8"))
    body.attach(MIMEText(html, "html", "utf-8"))
    if attachments:
        message = MIMEMultipart("mixed")
        message.attach(body)
        for attachment in attachments:
            message.attach(_attachment(attachment))
    message["Subject"] = f"[{settings.APP_NAME}] {subject}"
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    if priority in PRIORITY_HEADERS:
        message["X-Priority"] = PRIORITY_HEADERS[priority]
        message["X-MSMail-Priority"] = "High"
    return message


async def deliver(
    to_email: str,
    subject: str,
    html: str,
    to_name: str = "",
    text: str | None = None,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    attachments: Sequence[Attachment] = (),
) -> bool:
    """Envoie un courriel, l'objet préfixé du nom de l'application ; False sans SMTP configuré ou si l'envoi échoue."""
    if not settings.email_enabled:
        logger.warning("Email not configured, skipping email")
        return False
    try:
        message = _message(to_email, to_name, subject, html, text, priority, attachments)
        await asyncio.to_thread(_deliver, to_email, message.as_string())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False
    logger.info("Email sent to %s: %s", to_email, subject)
    return True


def _plain(body: str) -> str:
    return unescape(TAG.sub("", LINE_BREAK.sub("\n", LINK.sub(r"\2 : \1", body))))


def _text(subject: str, body: str) -> str:
    return f"""
{subject}

{_plain(body)}

---
Ceci est un message automatique de {settings.APP_NAME}.
Ne répondez pas à cet email.
"""


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
) -> bool:
    """Courriel de notification ; ``body`` est un fragment HTML dont la version texte est tirée, liens compris."""
    html = wrap(f"<h2>{escape(subject)}</h2>\n<p>{body}</p>", settings.APP_NAME)
    return await deliver(to_email, subject, html, to_name, _text(subject, body), priority)
