import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.alerts import asset_rules, portfolio_rules
from app.domains.alerts.models import PORTFOLIO_CONDITIONS, Alert, AlertCondition
from app.domains.alerts.pricing import asset_price
from app.domains.identity.models import User
from app.domains.notifications.models import NotificationPriority
from app.domains.notifications.repository import NotificationRepository
from app.domains.notifications.service import NotificationService
from app.domains.notifications.telegram.client import telegram_service
from app.domains.portfolio.models import Asset

logger = logging.getLogger(__name__)

PORTFOLIO_SYMBOL = "Portefeuille"
PRICE_CONDITIONS = frozenset({AlertCondition.PRICE_ABOVE, AlertCondition.PRICE_BELOW})


@dataclass
class AlertTrigger:
    """Déclenchement d'une alerte : valeur observée, seuil retenu et message à l'utilisateur."""

    alert_id: UUID
    alert_name: str
    symbol: str
    condition: str
    threshold: float
    current_value: float
    triggered_at: datetime
    message: str


def _trigger(alert: Alert, symbol: str, threshold: float, value: float, message: str) -> AlertTrigger:
    return AlertTrigger(
        alert_id=alert.id,
        alert_name=alert.name,
        symbol=symbol,
        condition=alert.condition.value,
        threshold=threshold,
        current_value=value,
        triggered_at=datetime.now(UTC),
        message=message,
    )


async def _evaluate_portfolio(db: AsyncSession, alert: Alert) -> AlertTrigger | None:
    threshold = float(alert.threshold)
    value, message = await portfolio_rules.RULES[alert.condition](db, alert, threshold)
    return _trigger(alert, PORTFOLIO_SYMBOL, threshold, value, message) if message else None


async def _assess(db: AsyncSession, alert: Alert) -> tuple[bool, AlertTrigger | None]:
    if alert.condition in PORTFOLIO_CONDITIONS:
        return True, await _evaluate_portfolio(db, alert)
    asset = (await db.execute(select(Asset).where(Asset.id == alert.asset_id))).scalar_one_or_none()
    if not asset:
        return False, None
    price = await asset_price(asset, alert.currency if alert.condition in PRICE_CONDITIONS else "EUR")
    if price == 0:
        return False, None
    outcome = await asset_rules.RULES[alert.condition](db, alert, asset, price)
    if outcome is None:
        return True, None
    threshold, message = outcome
    return True, _trigger(alert, asset.symbol, threshold, price, message)


async def evaluate(db: AsyncSession, alert: Alert) -> AlertTrigger | None:
    """Déclenchement de l'alerte s'il a lieu ; sans cours disponible, une alerte d'actif ne se déclenche pas.

    Un seuil de prix se compare au cours dans la devise de l'alerte ; les autres conditions, en euros.
    """
    return (await _assess(db, alert))[1]


async def _send_telegram(user: User | None, trigger: AlertTrigger, priority: NotificationPriority) -> None:
    try:
        if user and user.telegram_enabled and user.telegram_chat_id:
            await telegram_service.send_smart_alert(
                message=trigger.message,
                chat_id=user.telegram_chat_id,
                user_id=str(user.id),
                priority="critical" if priority == NotificationPriority.URGENT else "high",
                symbol=trigger.symbol,
                alert_type=trigger.condition,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram alert failed for %s: %s", trigger.symbol, exc)


async def _notify(db: AsyncSession, alert: Alert, trigger: AlertTrigger, user: User | None) -> None:
    alert.triggered_at = datetime.now(UTC)
    alert.triggered_count = (alert.triggered_count or 0) + 1
    urgent = alert.condition == AlertCondition.VOLATILITY_SPIKE
    priority = NotificationPriority.URGENT if urgent else NotificationPriority.HIGH
    await NotificationService(NotificationRepository(db)).send_alert(
        user_id=alert.user_id,
        alert_name=alert.name,
        message=trigger.message,
        alert_id=alert.id,
        notify_email=alert.notify_email,
        notify_in_app=alert.notify_in_app,
        priority=priority,
    )
    await _send_telegram(user, trigger, priority)


async def check_alerts(db: AsyncSession, user_id: str) -> list[AlertTrigger]:
    """Évalue les alertes actives de l'utilisateur et notifie celles dont la condition vient de devenir vraie.

    Une alerte déclenchée se désarme ; elle se réarme dès que sa condition est évaluée fausse, pas quand le
    cours manque.
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    alerts = (
        (await db.execute(select(Alert).where(Alert.user_id == user_id, Alert.is_active.is_(True)))).scalars().all()
    )
    triggered = []
    rearmed = False
    for alert in alerts:
        known, trigger = await _assess(db, alert)
        if trigger is None:
            if known and not alert.armed:
                alert.armed = True
                rearmed = True
        elif alert.armed:
            alert.armed = False
            triggered.append(trigger)
            await _notify(db, alert, trigger, user)
    if triggered or rearmed:
        await db.commit()
    return triggered


async def check_all_user_alerts(db: AsyncSession) -> dict[str, Any]:
    """Évalue les alertes de chaque utilisateur actif ; rend le nombre d'utilisateurs et de déclenchements."""
    user_ids = [str(uid) for uid in (await db.execute(select(User.id).where(User.is_active.is_(True)))).scalars().all()]
    total = 0
    for user_id in user_ids:
        total += len(await check_alerts(db, user_id))
    return {"users_checked": len(user_ids), "alerts_triggered": total}
