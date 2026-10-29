import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.config import settings
from app.domains.notifications.report_bodies import (
    alert_email,
    digest_email,
    monthly_email,
    monthly_pdf_name,
    weekly_email,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes


def _login_and_send(server: smtplib.SMTP, to_email: str, message: str) -> None:
    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
    server.sendmail(settings.SMTP_FROM_EMAIL, to_email, message)


def _deliver(to_email: str, message: str) -> None:
    context = ssl.create_default_context()
    if settings.SMTP_TLS:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls(context=context)
            _login_and_send(server, to_email, message)
    else:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context) as server:
            _login_and_send(server, to_email, message)


def _message(to_email: str, subject: str, html: str, attachments: list[Attachment]) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.attach(MIMEText(html, "html", "utf-8"))
    for attachment in attachments:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={attachment.filename}")
        message.attach(part)
    return message


class ReportMailer:
    """Courriels de rapport : seuil de prix franchi, rapports hebdomadaire et mensuel, résumé quotidien."""

    @property
    def is_configured(self) -> bool:
        return settings.email_enabled

    async def send_email(
        self, to_email: str, subject: str, html: str, attachments: list[Attachment] | None = None
    ) -> bool:
        """Envoie le courriel ; rend False sans SMTP configuré ou si l'envoi échoue."""
        if not self.is_configured:
            logger.warning("Email not configured, skipping send")
            return False
        try:
            message = _message(to_email, subject, html, attachments or [])
            await asyncio.to_thread(_deliver, to_email, message.as_string())
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send email to %s: %s", to_email, exc)
            return False
        logger.info("Email sent successfully to %s: %s", to_email, subject)
        return True

    async def send_alert_notification(
        self,
        to_email: str,
        alert_name: str,
        asset_symbol: str,
        current_price: float,
        target_price: float,
        condition: str,
        currency: str = "EUR",
    ) -> bool:
        return await self.send_email(
            to_email, *alert_email(alert_name, asset_symbol, current_price, target_price, condition, currency)
        )

    async def send_weekly_report(
        self,
        to_email: str,
        user_name: str,
        total_value: float,
        week_change: float,
        week_change_pct: float,
        top_performers: list[dict[str, Any]],
        worst_performers: list[dict[str, Any]],
        currency: str = "EUR",
    ) -> bool:
        subject, html = weekly_email(
            user_name, total_value, week_change, week_change_pct, top_performers, worst_performers, currency
        )
        return await self.send_email(to_email, subject, html)

    async def send_monthly_report(
        self,
        to_email: str,
        user_name: str,
        total_value: float,
        month_change: float,
        month_change_pct: float,
        ytd_change_pct: float,
        allocation: list[dict[str, Any]],
        currency: str = "EUR",
        pdf_content: bytes | None = None,
    ) -> bool:
        """Rapport mensuel, avec le rapport de performance PDF en pièce jointe quand il a pu être généré."""
        subject, html = monthly_email(
            user_name, total_value, month_change, month_change_pct, ytd_change_pct, allocation, currency
        )
        attachments = [Attachment(monthly_pdf_name(), pdf_content)] if pdf_content else None
        return await self.send_email(to_email, subject, html, attachments)

    async def send_digest(
        self,
        to_email: str,
        user_name: str,
        alerts_triggered: list[dict[str, Any]],
        predictions: list[dict[str, Any]],
        insights: list[str],
    ) -> bool:
        subject, html = digest_email(user_name, alerts_triggered, predictions, insights)
        return await self.send_email(to_email, subject, html)


report_mailer = ReportMailer()
