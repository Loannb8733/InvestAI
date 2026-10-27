import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.alerts.models import Alert
from app.domains.portfolio.models import Asset, Portfolio

ALERT_NOT_FOUND = "Alerte non trouvée"


async def owned_alert(db: AsyncSession, alert_id: uuid.UUID, user_id: uuid.UUID) -> Alert:
    """Alerte de l'utilisateur, ou 404."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ALERT_NOT_FOUND)
    return alert


async def user_alerts(db: AsyncSession, user_id: uuid.UUID, active_only: bool, skip: int, limit: int) -> list[Alert]:
    """Alertes de l'utilisateur, de la plus récente à la plus ancienne."""
    query = select(Alert).where(Alert.user_id == user_id)
    if active_only:
        query = query.where(Alert.is_active.is_(True))
    result = await db.execute(query.order_by(Alert.created_at.desc()).offset(skip).limit(limit))
    return list(result.scalars().all())


async def owned_asset(db: AsyncSession, asset_id: uuid.UUID | None, user_id: uuid.UUID) -> Asset | None:
    """Actif d'un portefeuille de l'utilisateur."""
    query = (
        select(Asset)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Asset.id == asset_id, Portfolio.user_id == user_id)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def assets_by_id(db: AsyncSession, asset_ids: set[uuid.UUID]) -> dict[uuid.UUID, Asset]:
    """Actifs désignés, par identifiant."""
    if not asset_ids:
        return {}
    result = await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    return {asset.id: asset for asset in result.scalars().all()}


async def alert_summary(db: AsyncSession, user_id: Any) -> dict[str, int]:
    """Nombre d'alertes, d'actives, de déclenchées aujourd'hui (UTC) et total des déclenchements."""
    alerts = (await db.execute(select(Alert).where(Alert.user_id == user_id))).scalars().all()
    today = datetime.now(UTC).date()
    return {
        "total_alerts": len(alerts),
        "active_alerts": sum(1 for a in alerts if a.is_active),
        "triggered_today": sum(1 for a in alerts if a.triggered_at and a.triggered_at.date() == today),
        "total_triggers": sum(a.triggered_count or 0 for a in alerts),
    }
