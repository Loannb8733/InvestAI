"""Alerts endpoints for price and performance notifications."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.alert import Alert, AlertCondition
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.alert_service import alert_service

router = APIRouter()


class AlertCreate(BaseModel):
    """Schema for creating an alert."""

    asset_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    condition: AlertCondition
    threshold: float = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=10)
    notify_email: bool = True
    notify_in_app: bool = True


class AlertUpdate(BaseModel):
    """Schema for updating an alert."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    threshold: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_in_app: Optional[bool] = None


class AlertResponse(BaseModel):
    """Alert response schema."""

    id: UUID
    asset_id: Optional[UUID]
    name: str
    condition: str
    threshold: float
    currency: str
    is_active: bool
    triggered_at: Optional[str]
    triggered_count: int
    notify_email: bool
    notify_in_app: bool
    created_at: datetime
    asset_symbol: Optional[str] = None
    asset_name: Optional[str] = None


class AlertTriggerResponse(BaseModel):
    """Alert trigger response."""

    alert_id: UUID
    alert_name: str
    symbol: str
    condition: str
    threshold: float
    current_value: float
    triggered_at: str
    message: str


class AlertSummaryResponse(BaseModel):
    """Alert summary response."""

    total_alerts: int
    active_alerts: int
    triggered_today: int
    total_triggers: int


class AlertConditionInfo(BaseModel):
    """Alert condition information."""

    value: str
    label: str
    description: str


@router.get("/conditions", response_model=List[AlertConditionInfo])
async def list_alert_conditions() -> List[AlertConditionInfo]:
    """List all available alert conditions."""
    conditions = [
        {
            "value": "price_above",
            "label": "Prix supérieur à",
            "description": "Alerte quand le prix dépasse un seuil",
        },
        {
            "value": "price_below",
            "label": "Prix inférieur à",
            "description": "Alerte quand le prix passe sous un seuil",
        },
        {
            "value": "change_percent_up",
            "label": "Hausse de X%",
            "description": "Alerte quand le gain dépasse un pourcentage",
        },
        {
            "value": "change_percent_down",
            "label": "Baisse de X%",
            "description": "Alerte quand la perte dépasse un pourcentage",
        },
        {
            "value": "daily_change_up",
            "label": "Hausse journalière de X%",
            "description": "Alerte sur la variation journalière positive",
        },
        {
            "value": "daily_change_down",
            "label": "Baisse journalière de X%",
            "description": "Alerte sur la variation journalière négative",
        },
    ]
    return [AlertConditionInfo(**c) for c in conditions]


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertSummaryResponse:
    """Get summary of user's alerts."""
    summary = await alert_service.get_alert_summary(db, str(current_user.id))
    return AlertSummaryResponse(**summary)


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    active_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AlertResponse]:
    """List all alerts for the current user."""
    query = select(Alert).where(Alert.user_id == current_user.id)

    if active_only:
        query = query.where(Alert.is_active == True)

    result = await db.execute(query.order_by(Alert.created_at.desc()))
    alerts = result.scalars().all()

    # Get asset info for each alert
    response = []
    for alert in alerts:
        asset_symbol = None
        asset_name = None

        if alert.asset_id:
            asset_result = await db.execute(
                select(Asset).where(Asset.id == alert.asset_id)
            )
            asset = asset_result.scalar_one_or_none()
            if asset:
                asset_symbol = asset.symbol
                asset_name = asset.name

        response.append(
            AlertResponse(
                id=alert.id,
                asset_id=alert.asset_id,
                name=alert.name,
                condition=alert.condition.value,
                threshold=float(alert.threshold),
                currency=alert.currency,
                is_active=alert.is_active,
                triggered_at=alert.triggered_at,
                triggered_count=int(alert.triggered_count or 0),
                notify_email=alert.notify_email,
                notify_in_app=alert.notify_in_app,
                created_at=alert.created_at,
                asset_symbol=asset_symbol,
                asset_name=asset_name,
            )
        )

    return response


@router.post("/", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_in: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Create a new alert."""
    # Verify asset belongs to user
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolios = result.scalars().all()
    portfolio_ids = [p.id for p in portfolios]

    result = await db.execute(
        select(Asset).where(
            Asset.id == alert_in.asset_id,
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actif non trouvé",
        )

    alert = Alert(
        user_id=current_user.id,
        asset_id=alert_in.asset_id,
        name=alert_in.name,
        condition=alert_in.condition,
        threshold=alert_in.threshold,
        currency=alert_in.currency,
        is_active=True,
        notify_email=alert_in.notify_email,
        notify_in_app=alert_in.notify_in_app,
    )

    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    return AlertResponse(
        id=alert.id,
        asset_id=alert.asset_id,
        name=alert.name,
        condition=alert.condition.value,
        threshold=float(alert.threshold),
        currency=alert.currency,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at,
        triggered_count=int(alert.triggered_count or 0),
        notify_email=alert.notify_email,
        notify_in_app=alert.notify_in_app,
        created_at=alert.created_at,
        asset_symbol=asset.symbol,
        asset_name=asset.name,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Get a specific alert."""
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.user_id == current_user.id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerte non trouvée",
        )

    asset_symbol = None
    asset_name = None

    if alert.asset_id:
        asset_result = await db.execute(
            select(Asset).where(Asset.id == alert.asset_id)
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset_symbol = asset.symbol
            asset_name = asset.name

    return AlertResponse(
        id=alert.id,
        asset_id=alert.asset_id,
        name=alert.name,
        condition=alert.condition.value,
        threshold=float(alert.threshold),
        currency=alert.currency,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at,
        triggered_count=int(alert.triggered_count or 0),
        notify_email=alert.notify_email,
        notify_in_app=alert.notify_in_app,
        created_at=alert.created_at,
        asset_symbol=asset_symbol,
        asset_name=asset_name,
    )


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    alert_in: AlertUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Update an alert."""
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.user_id == current_user.id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerte non trouvée",
        )

    if alert_in.name is not None:
        alert.name = alert_in.name
    if alert_in.threshold is not None:
        alert.threshold = alert_in.threshold
    if alert_in.is_active is not None:
        alert.is_active = alert_in.is_active
    if alert_in.notify_email is not None:
        alert.notify_email = alert_in.notify_email
    if alert_in.notify_in_app is not None:
        alert.notify_in_app = alert_in.notify_in_app

    await db.commit()
    await db.refresh(alert)

    asset_symbol = None
    asset_name = None

    if alert.asset_id:
        asset_result = await db.execute(
            select(Asset).where(Asset.id == alert.asset_id)
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset_symbol = asset.symbol
            asset_name = asset.name

    return AlertResponse(
        id=alert.id,
        asset_id=alert.asset_id,
        name=alert.name,
        condition=alert.condition.value,
        threshold=float(alert.threshold),
        currency=alert.currency,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at,
        triggered_count=int(alert.triggered_count or 0),
        notify_email=alert.notify_email,
        notify_in_app=alert.notify_in_app,
        created_at=alert.created_at,
        asset_symbol=asset_symbol,
        asset_name=asset_name,
    )


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert."""
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.user_id == current_user.id,
        )
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerte non trouvée",
        )

    await db.delete(alert)
    await db.commit()


@router.post("/check", response_model=List[AlertTriggerResponse])
async def check_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AlertTriggerResponse]:
    """Manually check all alerts and return triggered ones."""
    triggered = await alert_service.check_alerts(db, str(current_user.id))

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
