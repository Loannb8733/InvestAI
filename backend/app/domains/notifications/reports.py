import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.notifications.models import NotificationType
from app.domains.notifications.report_mailer import report_mailer
from app.domains.notifications.repository import NotificationRepository, Recipient
from app.domains.reports.performance_pdf import render_performance_pdf
from app.domains.reports.service import report_service
from app.services.metrics_service import metrics_service
from app.services.snapshot_service import snapshot_service

logger = logging.getLogger(__name__)

NOT_CONFIGURED = {"sent": 0, "failed": 0, "skipped": "email_not_configured"}
WEEK_DAYS = 7
MONTH_DAYS = 30
YEAR_DAYS = 365

Report = Callable[[AsyncSession, Recipient], Awaitable[bool | None]]


def _display_name(recipient: Recipient) -> str:
    full_name = f"{recipient.first_name or ''} {recipient.last_name or ''}".strip()
    return full_name or recipient.email.split("@")[0]


async def _send_each(db: AsyncSession, recipients: list[Recipient], report: Report, label: str) -> dict[str, Any]:
    sent = failed = 0
    for recipient in recipients:
        try:
            outcome = await report(db, recipient)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send %s to %s: %s", label, recipient.email, exc)
            failed += 1
            continue
        if outcome is None:
            continue
        if outcome:
            sent += 1
            logger.info("%s sent to %s", label, recipient.email)
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


async def _period_change(db: AsyncSession, user_id: str, total_value: float, days: int) -> tuple[float, float]:
    history = await snapshot_service.build_portfolio_value_series(db, user_id, days=days)
    start_value = history[0]["value"] if history else total_value
    change = total_value - start_value
    return change, (change / start_value * 100) if start_value > 0 else 0


async def _ytd_change_pct(db: AsyncSession, user_id: str, metrics: dict[str, Any]) -> float:
    history = await snapshot_service.build_portfolio_value_series(db, user_id, days=YEAR_DAYS)
    year_start = f"{datetime.now().year}-01-01"
    start_value = next((p["value"] for p in history if p["full_date"][:10] >= year_start), metrics["total_invested"])
    return float((metrics["total_value"] - start_value) / start_value * 100) if start_value > 0 else 0


def _allocation(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    total = metrics["total_value"]
    allocation = [
        {
            "symbol": asset.get("symbol", "?"),
            "allocation_pct": (asset.get("current_value", 0) / total * 100) if total > 0 else 0,
            "value": asset.get("current_value", 0),
        }
        for asset in metrics.get("assets", [])
    ]
    return sorted(allocation, key=lambda line: line["value"], reverse=True)


async def _performance_pdf(db: AsyncSession, recipient: Recipient) -> bytes | None:
    try:
        return render_performance_pdf(await report_service.get_report_data(db, str(recipient.id)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate PDF for %s: %s", recipient.email, exc)
        return None


def _performers(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"symbol": asset["symbol"], "change_pct": asset["gain_loss_percent"]} for asset in ranked]


async def _weekly(db: AsyncSession, recipient: Recipient) -> bool | None:
    metrics = await metrics_service.get_user_dashboard_metrics(db, str(recipient.id), days=WEEK_DAYS)
    if metrics["total_value"] == 0:
        return None
    change, change_pct = await _period_change(db, str(recipient.id), metrics["total_value"], WEEK_DAYS)
    return await report_mailer.send_weekly_report(
        to_email=recipient.email,
        user_name=_display_name(recipient),
        total_value=metrics["total_value"],
        week_change=change,
        week_change_pct=change_pct,
        top_performers=_performers(metrics["top_performers"]),
        worst_performers=_performers(metrics["worst_performers"]),
    )


async def _monthly(db: AsyncSession, recipient: Recipient) -> bool | None:
    metrics = await metrics_service.get_user_dashboard_metrics(db, str(recipient.id))
    if metrics["total_value"] == 0:
        return None
    change, change_pct = await _period_change(db, str(recipient.id), metrics["total_value"], MONTH_DAYS)
    return await report_mailer.send_monthly_report(
        to_email=recipient.email,
        user_name=_display_name(recipient),
        total_value=metrics["total_value"],
        month_change=change,
        month_change_pct=change_pct,
        ytd_change_pct=await _ytd_change_pct(db, str(recipient.id), metrics),
        allocation=_allocation(metrics),
        pdf_content=await _performance_pdf(db, recipient),
    )


async def weekly_reports(db: AsyncSession) -> dict[str, Any]:
    """Rapport hebdomadaire à chaque détenteur d'un portefeuille non vide ; rend les envois réussis et échoués."""
    if not report_mailer.is_configured:
        logger.warning("Email not configured, skipping weekly reports")
        return dict(NOT_CONFIGURED)
    return await _send_each(db, await NotificationRepository(db).portfolio_owners(), _weekly, "Weekly report")


async def monthly_reports(db: AsyncSession) -> dict[str, Any]:
    """Rapport mensuel, PDF de performance joint, à chaque détenteur d'un portefeuille non vide."""
    if not report_mailer.is_configured:
        logger.warning("Email not configured, skipping monthly reports")
        return dict(NOT_CONFIGURED)
    return await _send_each(db, await NotificationRepository(db).portfolio_owners(), _monthly, "Monthly report")


async def daily_digest(db: AsyncSession) -> dict[str, Any]:
    """Résumé des alertes des dernières 24 h à chaque utilisateur notifié pendant ce temps."""
    if not report_mailer.is_configured:
        return dict(NOT_CONFIGURED)
    since = datetime.now(UTC) - timedelta(days=1)

    async def digest(session: AsyncSession, recipient: Recipient) -> bool | None:
        notifications = await NotificationRepository(session).received_since(recipient.id, since)
        alerts = [
            {"title": n.title, "message": n.message}
            for n in notifications
            if n.type == NotificationType.ALERT_TRIGGERED
        ]
        if not alerts:
            return None
        return await report_mailer.send_digest(recipient.email, _display_name(recipient), alerts)

    return await _send_each(db, await NotificationRepository(db).notified_since(since), digest, "Daily digest")
