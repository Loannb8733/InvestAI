"""Alert service for price and performance notifications."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertCondition
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.price_service import PriceService
from app.services.notification_service import notification_service


@dataclass
class AlertTrigger:
    """Alert trigger information."""

    alert_id: UUID
    alert_name: str
    symbol: str
    condition: str
    threshold: float
    current_value: float
    triggered_at: datetime
    message: str


class AlertService:
    """Service for managing and checking alerts."""

    def __init__(self):
        self.price_service = PriceService()

    async def check_alerts(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[AlertTrigger]:
        """Check all active alerts for a user and return triggered ones."""
        triggered = []

        # Get user's active alerts
        result = await db.execute(
            select(Alert).where(
                Alert.user_id == user_id,
                Alert.is_active == True,
            )
        )
        alerts = result.scalars().all()

        for alert in alerts:
            trigger = await self._check_single_alert(db, alert)
            if trigger:
                triggered.append(trigger)

                # Update alert
                alert.triggered_at = datetime.utcnow()
                alert.triggered_count = (alert.triggered_count or 0) + 1

                # Send notification
                await notification_service.send_alert_notification(
                    db=db,
                    user_id=alert.user_id,
                    alert_name=alert.name,
                    symbol=trigger.symbol,
                    message=trigger.message,
                    alert_id=alert.id,
                    notify_email=alert.notify_email,
                    notify_in_app=alert.notify_in_app,
                )

        if triggered:
            await db.commit()

        return triggered

    async def check_all_user_alerts(
        self,
        db: AsyncSession,
    ) -> dict:
        """Check alerts for all users (for background task)."""
        from app.models.user import User

        result = await db.execute(select(User.id).where(User.is_active == True))
        user_ids = [str(uid) for uid in result.scalars().all()]

        total_checked = 0
        total_triggered = 0

        for user_id in user_ids:
            triggered = await self.check_alerts(db, user_id)
            total_checked += 1
            total_triggered += len(triggered)

        return {
            "users_checked": total_checked,
            "alerts_triggered": total_triggered,
        }

    async def create_alert(
        self,
        db: AsyncSession,
        user_id: str,
        asset_id: str,
        name: str,
        condition: AlertCondition,
        threshold: float,
        currency: str = "EUR",
        notify_email: bool = True,
        notify_in_app: bool = True,
    ) -> Alert:
        """Create a new alert."""
        # Verify asset belongs to user
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        result = await db.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        asset = result.scalar_one_or_none()

        if not asset:
            raise ValueError("Asset not found")

        alert = Alert(
            user_id=user_id,
            asset_id=asset_id,
            name=name,
            condition=condition,
            threshold=Decimal(str(threshold)),
            currency=currency,
            is_active=True,
            notify_email=notify_email,
            notify_in_app=notify_in_app,
        )

        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        return alert

    async def _check_single_alert(
        self,
        db: AsyncSession,
        alert: Alert,
    ) -> Optional[AlertTrigger]:
        """Check if a single alert should trigger."""
        # Get asset
        result = await db.execute(
            select(Asset).where(Asset.id == alert.asset_id)
        )
        asset = result.scalar_one_or_none()

        if not asset:
            return None

        # Get current price
        current_price = await self._get_asset_price(asset)

        if current_price == 0:
            return None

        threshold = float(alert.threshold)
        should_trigger = False
        message = ""

        if alert.condition == AlertCondition.PRICE_ABOVE:
            if current_price > threshold:
                should_trigger = True
                message = f"{asset.symbol} a dépassé {threshold} {alert.currency} (actuel: {current_price:.2f})"

        elif alert.condition == AlertCondition.PRICE_BELOW:
            if current_price < threshold:
                should_trigger = True
                message = f"{asset.symbol} est passé sous {threshold} {alert.currency} (actuel: {current_price:.2f})"

        elif alert.condition == AlertCondition.CHANGE_PERCENT_UP:
            avg_price = float(asset.avg_buy_price)
            if avg_price > 0:
                change = (current_price - avg_price) / avg_price * 100
                if change >= threshold:
                    should_trigger = True
                    message = f"{asset.symbol} a augmenté de {change:.1f}% (seuil: {threshold}%)"

        elif alert.condition == AlertCondition.CHANGE_PERCENT_DOWN:
            avg_price = float(asset.avg_buy_price)
            if avg_price > 0:
                change = (current_price - avg_price) / avg_price * 100
                if change <= -threshold:
                    should_trigger = True
                    message = f"{asset.symbol} a baissé de {abs(change):.1f}% (seuil: {threshold}%)"

        elif alert.condition == AlertCondition.DAILY_CHANGE_UP:
            # Would need previous day price - simulate
            daily_change = 2.5  # Simulated
            if daily_change >= threshold:
                should_trigger = True
                message = f"{asset.symbol} hausse journalière de {daily_change:.1f}% (seuil: {threshold}%)"

        elif alert.condition == AlertCondition.DAILY_CHANGE_DOWN:
            daily_change = -3.0  # Simulated
            if daily_change <= -threshold:
                should_trigger = True
                message = f"{asset.symbol} baisse journalière de {abs(daily_change):.1f}% (seuil: {threshold}%)"

        if should_trigger:
            return AlertTrigger(
                alert_id=alert.id,
                alert_name=alert.name,
                symbol=asset.symbol,
                condition=alert.condition.value,
                threshold=threshold,
                current_value=current_price,
                triggered_at=datetime.utcnow(),
                message=message,
            )

        return None

    async def _get_asset_price(self, asset: Asset) -> float:
        """Get current price for an asset."""
        try:
            if asset.asset_type == AssetType.CRYPTO:
                return await self.price_service.get_crypto_price(asset.symbol)
            elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                return await self.price_service.get_stock_price(asset.symbol)
            else:
                return float(asset.avg_buy_price)
        except Exception:
            return float(asset.avg_buy_price)

    async def get_alert_summary(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> dict:
        """Get summary of user's alerts."""
        result = await db.execute(
            select(Alert).where(Alert.user_id == user_id)
        )
        alerts = result.scalars().all()

        active_count = sum(1 for a in alerts if a.is_active)
        triggered_today = sum(
            1 for a in alerts
            if a.triggered_at and a.triggered_at.date() == datetime.utcnow().date()
        )
        total_triggered = sum(a.triggered_count or 0 for a in alerts)

        return {
            "total_alerts": len(alerts),
            "active_alerts": active_count,
            "triggered_today": triggered_today,
            "total_triggers": total_triggered,
        }


# Singleton instance
alert_service = AlertService()
