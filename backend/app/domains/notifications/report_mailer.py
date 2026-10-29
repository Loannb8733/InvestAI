from typing import Any

from app.core.config import settings
from app.domains.notifications.mail import Attachment, deliver
from app.domains.notifications.report_bodies import digest_email, monthly_email, monthly_pdf_name, weekly_email


class ReportMailer:
    """Courriels de rapport : rapports hebdomadaire et mensuel, résumé quotidien des alertes."""

    @property
    def is_configured(self) -> bool:
        return settings.email_enabled

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
        """Rapport hebdomadaire ; chaque actif classé porte ``symbol`` et ``change_pct``, sa variation sur 7 jours."""
        subject, html = weekly_email(
            user_name, total_value, week_change, week_change_pct, top_performers, worst_performers, currency
        )
        return await deliver(to_email, subject, html)

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
        attachments = [Attachment(monthly_pdf_name(), pdf_content)] if pdf_content else []
        return await deliver(to_email, subject, html, attachments=attachments)

    async def send_digest(self, to_email: str, user_name: str, alerts: list[dict[str, str]]) -> bool:
        """Résumé quotidien ; chaque alerte porte le ``title`` et le ``message`` de sa notification."""
        subject, html = digest_email(user_name, alerts)
        return await deliver(to_email, subject, html)


report_mailer = ReportMailer()
