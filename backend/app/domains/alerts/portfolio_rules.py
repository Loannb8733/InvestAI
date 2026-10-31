from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.alerts.models import Alert, AlertCondition
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.snapshots.service import snapshot_service
from app.domains.identity.models import User
from app.domains.reports.service import report_service

Outcome = tuple[float, str | None]
Rule = Callable[[AsyncSession, Alert, float], Awaitable[Outcome]]

DRAWDOWN_DAYS = 365


async def _drawdown(db: AsyncSession, alert: Alert, threshold: float) -> Outcome:
    history = await snapshot_service.build_portfolio_value_series(db, str(alert.user_id), days=DRAWDOWN_DAYS)
    values = [float(point.get("value") or 0) for point in history if (point.get("value") or 0) > 0]
    if len(values) < 2:
        return 0.0, None
    peak, current = max(values), values[-1]
    drawdown = (peak - current) / peak * 100 if peak > 0 else 0.0
    message = None
    if drawdown >= threshold:
        message = (
            f"\U0001f4c9 Repli de {drawdown:.1f}% depuis le plus-haut du portefeuille "
            f"(seuil d'alerte : {threshold:.0f}%). Pic : {peak:,.0f}€, actuel : {current:,.0f}€."
        )
    return round(drawdown, 2), message


async def _concentration(db: AsyncSession, alert: Alert, threshold: float) -> Outcome:
    metrics = await metrics_service.get_user_dashboard_metrics(db, str(alert.user_id))
    assets = metrics.get("aggregated_assets", [])
    total = sum(float(a.get("current_value") or 0) for a in assets)
    if total <= 0:
        return 0.0, None
    hhi = sum((float(a.get("current_value") or 0) / total) ** 2 for a in assets)
    message = None
    if hhi >= threshold:
        top = max(assets, key=lambda a: float(a.get("current_value") or 0), default=None)
        top_text = f" Position dominante : {top.get('symbol')}." if top else ""
        message = (
            f"⚠️ Concentration élevée du portefeuille (HHI {hhi:.2f}, seuil {threshold:.2f}).{top_text} "
            "Envisage de diversifier."
        )
    return round(hhi, 4), message


async def _drift(db: AsyncSession, alert: Alert, threshold: float) -> Outcome:
    user = (await db.execute(select(User).where(User.id == alert.user_id))).scalar_one_or_none()
    targets = getattr(user, "target_allocations", None) if user else None
    if not targets:
        return 0.0, None
    currency = getattr(user, "preferred_currency", "EUR") or "EUR"
    report = await report_service.get_rebalancing_report(
        db, str(alert.user_id), targets, currency=currency, estimate_tax=False
    )
    if not report.categories:
        return 0.0, None
    worst = max(report.categories, key=lambda c: abs(c["drift_pct"]))
    drift = abs(worst["drift_pct"])
    message = None
    if drift >= threshold:
        message = (
            f"\U0001f3af Allocation dérivée : {worst['label']} à {worst['current_pct']:.0f}% "
            f"(cible {worst['target_pct']:.0f}%, écart {drift:.0f} pts ≥ {threshold:.0f}). "
            "Un rééquilibrage est conseillé."
        )
    return round(drift, 2), message


RULES: dict[AlertCondition, Rule] = {
    AlertCondition.PORTFOLIO_DRAWDOWN: _drawdown,
    AlertCondition.CONCENTRATION_HHI: _concentration,
    AlertCondition.ALLOCATION_DRIFT: _drift,
}
