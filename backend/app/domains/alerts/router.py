from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.alerts.catalog import CONDITIONS
from app.domains.alerts.checker import check_alerts
from app.domains.alerts.models import PORTFOLIO_CONDITIONS, Alert
from app.domains.alerts.repository import alert_summary, assets_by_id, owned_alert, owned_asset, user_alerts
from app.domains.alerts.schemas import (
    AlertConditionInfo,
    AlertCreate,
    AlertResponse,
    AlertSummaryResponse,
    AlertTriggerResponse,
    AlertUpdate,
)
from app.domains.identity.dependencies import CurrentUser
from app.domains.portfolio.models import Asset

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def _response(alert: Alert, asset: Asset | None) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        asset_id=alert.asset_id,
        name=alert.name,
        condition=alert.condition.value,
        threshold=float(alert.threshold),
        currency=alert.currency,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
        triggered_count=int(alert.triggered_count or 0),
        notify_email=alert.notify_email,
        notify_in_app=alert.notify_in_app,
        created_at=alert.created_at,
        asset_symbol=asset.symbol if asset else None,
        asset_name=asset.name if asset else None,
    )


async def _with_asset(session: AsyncSession, alert: Alert) -> AlertResponse:
    assets = await assets_by_id(session, {alert.asset_id} if alert.asset_id else set())
    return _response(alert, assets.get(alert.asset_id) if alert.asset_id else None)


@router.get("/conditions", response_model=list[AlertConditionInfo])
async def list_alert_conditions() -> list[AlertConditionInfo]:
    """Conditions d'alerte proposées à l'écran."""
    return list(CONDITIONS)


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(user: CurrentUser, session: Session) -> AlertSummaryResponse:
    """Compteurs des alertes de l'utilisateur."""
    return AlertSummaryResponse(**await alert_summary(session, str(user.id)))


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    user: CurrentUser, session: Session, active_only: bool = False, skip: int = 0, limit: int = 50
) -> list[AlertResponse]:
    """Alertes de l'utilisateur, de la plus récente à la plus ancienne, avec l'actif visé."""
    alerts = await user_alerts(session, user.id, active_only, skip, limit)
    assets = await assets_by_id(session, {a.asset_id for a in alerts if a.asset_id})
    return [_response(alert, assets.get(alert.asset_id) if alert.asset_id else None) for alert in alerts]


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(alert_in: AlertCreate, user: CurrentUser, session: Session) -> AlertResponse:
    """Crée une alerte sur un actif de l'utilisateur, ou sur son portefeuille."""
    asset = None
    if alert_in.condition not in PORTFOLIO_CONDITIONS:
        asset = await owned_asset(session, alert_in.asset_id, user.id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actif non trouvé")
    alert = Alert(
        user_id=user.id,
        asset_id=alert_in.asset_id,
        name=alert_in.name,
        condition=alert_in.condition,
        threshold=alert_in.threshold,
        currency=alert_in.currency,
        is_active=True,
        notify_email=alert_in.notify_email,
        notify_in_app=alert_in.notify_in_app,
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return _response(alert, asset)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: UUID, user: CurrentUser, session: Session) -> AlertResponse:
    """Alerte de l'utilisateur avec l'actif visé."""
    return await _with_asset(session, await owned_alert(session, alert_id, user.id))


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(alert_id: UUID, alert_in: AlertUpdate, user: CurrentUser, session: Session) -> AlertResponse:
    """Modifie nom, seuil, activation ou canaux d'une alerte ; un nouveau seuil ou une réactivation la réarme."""
    alert = await owned_alert(session, alert_id, user.id)
    changes = alert_in.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(alert, field, value)
    if "threshold" in changes or changes.get("is_active"):
        alert.armed = True
    await session.commit()
    await session.refresh(alert)
    return await _with_asset(session, alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: UUID, user: CurrentUser, session: Session) -> None:
    """Supprime une alerte de l'utilisateur."""
    await session.delete(await owned_alert(session, alert_id, user.id))
    await session.commit()


@router.post("/check", response_model=list[AlertTriggerResponse])
@limiter.limit("3/minute")
async def check_user_alerts(request: Request, user: CurrentUser, session: Session) -> list[AlertTriggerResponse]:
    """Évalue tout de suite les alertes de l'utilisateur et rend celles qui se déclenchent."""
    triggered = await check_alerts(session, str(user.id))
    return [
        AlertTriggerResponse(
            alert_id=t.alert_id,
            alert_name=t.alert_name,
            symbol=t.symbol,
            condition=t.condition,
            threshold=t.threshold,
            current_value=t.current_value,
            triggered_at=t.triggered_at.isoformat(),
            message=t.message,
        )
        for t in triggered
    ]
