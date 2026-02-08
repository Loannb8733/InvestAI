"""Email service for sending notifications and reports."""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_TLS

    @property
    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return settings.email_enabled

    def _get_base_template(self, content: str, title: str = "InvestAI") -> str:
        """Wrap content in base HTML template."""
        return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #1a1a2e;
            background-color: #f5f5f5;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 24px;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 16px 24px;
            text-align: center;
            font-size: 12px;
            color: #6c757d;
        }}
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            margin: 16px 0;
        }}
        .alert-box {{
            padding: 16px;
            border-radius: 6px;
            margin: 16px 0;
        }}
        .alert-success {{ background-color: #d4edda; color: #155724; }}
        .alert-warning {{ background-color: #fff3cd; color: #856404; }}
        .alert-danger {{ background-color: #f8d7da; color: #721c24; }}
        .alert-info {{ background-color: #d1ecf1; color: #0c5460; }}
        .metric {{
            display: inline-block;
            padding: 8px 16px;
            background-color: #f8f9fa;
            border-radius: 4px;
            margin: 4px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: 600;
            color: #667eea;
        }}
        .metric-label {{
            font-size: 12px;
            color: #6c757d;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
        }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>Cet email a ete envoye automatiquement par InvestAI.</p>
            <p>&copy; {datetime.now().year} InvestAI - Votre assistant d'investissement</p>
        </div>
    </div>
</body>
</html>
"""

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text fallback (optional)
            attachments: List of dicts with 'filename', 'content', 'content_type'

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.warning("Email not configured, skipping send")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            # Add text part (fallback)
            if text_content:
                part_text = MIMEText(text_content, "plain", "utf-8")
                msg.attach(part_text)

            # Add HTML part
            part_html = MIMEText(html_content, "html", "utf-8")
            msg.attach(part_html)

            # Add attachments
            if attachments:
                for attachment in attachments:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment["content"])
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={attachment['filename']}",
                    )
                    msg.attach(part)

            # Send email
            context = ssl.create_default_context()

            if self.use_tls:
                with smtplib.SMTP(self.host, self.port) as server:
                    server.starttls(context=context)
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, msg.as_string())
            else:
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

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
        """Send an alert notification email."""
        condition_text = "atteint" if condition == "above" else "descendu sous"
        alert_class = "alert-success" if condition == "above" else "alert-warning"

        content = f"""
        <h2>Alerte declenchee</h2>
        <div class="alert-box {alert_class}">
            <strong>{alert_name}</strong><br>
            {asset_symbol} a {condition_text} votre seuil de {target_price:.2f} {currency}
        </div>
        <p>Prix actuel: <strong>{current_price:.2f} {currency}</strong></p>
        <p>Seuil configure: <strong>{target_price:.2f} {currency}</strong></p>
        <a href="#" class="button">Voir le portefeuille</a>
        """

        html = self._get_base_template(content, f"Alerte: {asset_symbol}")
        return await self.send_email(
            to_email,
            f"[InvestAI] Alerte: {asset_symbol} {condition_text} {target_price:.2f} {currency}",
            html,
        )

    async def send_weekly_report(
        self,
        to_email: str,
        user_name: str,
        total_value: float,
        total_invested: float,
        week_change: float,
        week_change_pct: float,
        top_performers: List[Dict],
        worst_performers: List[Dict],
        currency: str = "EUR",
    ) -> bool:
        """Send weekly portfolio performance report."""
        change_class = "positive" if week_change >= 0 else "negative"
        change_sign = "+" if week_change >= 0 else ""

        # Build performers tables
        top_rows = ""
        for p in top_performers[:3]:
            top_rows += f"""
            <tr>
                <td>{p['symbol']}</td>
                <td class="positive">+{p['change_pct']:.1f}%</td>
            </tr>
            """

        worst_rows = ""
        for p in worst_performers[:3]:
            worst_rows += f"""
            <tr>
                <td>{p['symbol']}</td>
                <td class="negative">{p['change_pct']:.1f}%</td>
            </tr>
            """

        content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre resume hebdomadaire de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{total_value:,.2f} {currency}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {change_class}">{change_sign}{week_change:,.2f} {currency}</div>
                <div class="metric-label">Cette semaine ({change_sign}{week_change_pct:.1f}%)</div>
            </div>
        </div>

        <h3>Top performers</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{top_rows if top_rows else '<tr><td colspan="2">Aucune donnee</td></tr>'}</tbody>
        </table>

        <h3>Moins bons performers</h3>
        <table>
            <thead><tr><th>Actif</th><th>Performance</th></tr></thead>
            <tbody>{worst_rows if worst_rows else '<tr><td colspan="2">Aucune donnee</td></tr>'}</tbody>
        </table>

        <a href="#" class="button">Voir le dashboard complet</a>
        """

        html = self._get_base_template(content, "Rapport Hebdomadaire")
        return await self.send_email(
            to_email,
            f"[InvestAI] Rapport hebdomadaire - {change_sign}{week_change_pct:.1f}%",
            html,
        )

    async def send_monthly_report(
        self,
        to_email: str,
        user_name: str,
        total_value: float,
        total_invested: float,
        month_change: float,
        month_change_pct: float,
        ytd_change_pct: float,
        allocation: List[Dict],
        currency: str = "EUR",
        pdf_content: Optional[bytes] = None,
    ) -> bool:
        """Send monthly portfolio report with optional PDF attachment."""
        change_class = "positive" if month_change >= 0 else "negative"
        change_sign = "+" if month_change >= 0 else ""
        ytd_class = "positive" if ytd_change_pct >= 0 else "negative"
        ytd_sign = "+" if ytd_change_pct >= 0 else ""

        # Build allocation table
        alloc_rows = ""
        for a in allocation[:10]:
            alloc_rows += f"""
            <tr>
                <td>{a['symbol']}</td>
                <td>{a['allocation_pct']:.1f}%</td>
                <td>{a['value']:,.2f} {currency}</td>
            </tr>
            """

        content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre rapport mensuel de performance.</p>

        <div style="text-align: center; margin: 24px 0;">
            <div class="metric">
                <div class="metric-value">{total_value:,.2f} {currency}</div>
                <div class="metric-label">Valeur totale</div>
            </div>
            <div class="metric">
                <div class="metric-value {change_class}">{change_sign}{month_change_pct:.1f}%</div>
                <div class="metric-label">Ce mois</div>
            </div>
            <div class="metric">
                <div class="metric-value {ytd_class}">{ytd_sign}{ytd_change_pct:.1f}%</div>
                <div class="metric-label">Depuis le debut de l'annee</div>
            </div>
        </div>

        <h3>Repartition du portefeuille</h3>
        <table>
            <thead><tr><th>Actif</th><th>Allocation</th><th>Valeur</th></tr></thead>
            <tbody>{alloc_rows if alloc_rows else '<tr><td colspan="3">Aucune donnee</td></tr>'}</tbody>
        </table>

        <a href="#" class="button">Voir le rapport complet</a>
        """

        html = self._get_base_template(content, "Rapport Mensuel")

        attachments = None
        if pdf_content:
            attachments = [{
                "filename": f"rapport_mensuel_{datetime.now().strftime('%Y_%m')}.pdf",
                "content": pdf_content,
                "content_type": "application/pdf",
            }]

        return await self.send_email(
            to_email,
            f"[InvestAI] Rapport mensuel - {change_sign}{month_change_pct:.1f}%",
            html,
            attachments=attachments,
        )

    async def send_digest(
        self,
        to_email: str,
        user_name: str,
        alerts_triggered: List[Dict],
        predictions: List[Dict],
        insights: List[str],
    ) -> bool:
        """Send daily digest email with alerts, predictions and insights."""
        # Build alerts section
        alerts_html = ""
        if alerts_triggered:
            alerts_html = "<h3>Alertes declenchees</h3><ul>"
            for alert in alerts_triggered:
                alerts_html += f"<li><strong>{alert['symbol']}</strong>: {alert['message']}</li>"
            alerts_html += "</ul>"

        # Build predictions section
        predictions_html = ""
        if predictions:
            predictions_html = "<h3>Predictions du jour</h3><table>"
            predictions_html += "<thead><tr><th>Actif</th><th>Prediction 7j</th><th>Confiance</th></tr></thead><tbody>"
            for pred in predictions[:5]:
                pred_class = "positive" if pred['predicted_change'] >= 0 else "negative"
                sign = "+" if pred['predicted_change'] >= 0 else ""
                predictions_html += f"""
                <tr>
                    <td>{pred['symbol']}</td>
                    <td class="{pred_class}">{sign}{pred['predicted_change']:.1f}%</td>
                    <td>{pred['confidence']:.0f}%</td>
                </tr>
                """
            predictions_html += "</tbody></table>"

        # Build insights section
        insights_html = ""
        if insights:
            insights_html = "<h3>Insights</h3><ul>"
            for insight in insights[:5]:
                insights_html += f"<li>{insight}</li>"
            insights_html += "</ul>"

        content = f"""
        <h2>Bonjour {user_name},</h2>
        <p>Voici votre resume quotidien.</p>

        {alerts_html}
        {predictions_html}
        {insights_html}

        <a href="#" class="button">Acceder au dashboard</a>
        """

        html = self._get_base_template(content, "Resume Quotidien")
        return await self.send_email(
            to_email,
            f"[InvestAI] Resume du {datetime.now().strftime('%d/%m/%Y')}",
            html,
        )


# Singleton instance
email_service = EmailService()
