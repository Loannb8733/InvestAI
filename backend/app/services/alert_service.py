"""Alert service for price and performance notifications."""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import Alert, AlertCondition
from app.models.asset import Asset, AssetType
from app.models.notification import NotificationPriority
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.notification_service import notification_service
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)

_RISK_WEIGHT_TTL = 172800  # 48 hours


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
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy init Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------
    # Redis helpers for risk weight snapshots
    # ------------------------------------------------------------------

    async def _cache_risk_weight(self, symbol: str, date_str: str, risk_weight: float) -> None:
        """Cache a risk weight snapshot in Redis."""
        try:
            r = await self._get_redis()
            key = f"riskweight:{symbol.upper()}:{date_str}"
            await r.setex(key, _RISK_WEIGHT_TTL, json.dumps({"risk_weight": risk_weight}))
        except Exception as e:
            logger.debug("Failed to cache risk weight for %s: %s", symbol, e)

    async def _get_cached_risk_weight(self, symbol: str, date_str: str) -> Optional[float]:
        """Get cached risk weight snapshot from Redis."""
        try:
            r = await self._get_redis()
            data = await r.get(f"riskweight:{symbol.upper()}:{date_str}")
            if data:
                return json.loads(data).get("risk_weight")
        except Exception as e:
            logger.debug("Redis miss for risk weight %s: %s", symbol, e)
        return None

    # ------------------------------------------------------------------
    # Break-even computation
    # ------------------------------------------------------------------

    async def _compute_breakeven_price(self, db: AsyncSession, asset: Asset) -> Optional[float]:
        """Compute break-even price: (total_invested + fees) / quantity."""
        qty = float(asset.quantity)
        if qty <= 0:
            return None

        total_invested = qty * float(asset.avg_buy_price)

        fee_result = await db.execute(
            select(
                func.sum(
                    case(
                        (
                            Transaction.transaction_type == TransactionType.FEE,
                            Transaction.quantity * Transaction.price,
                        ),
                        else_=func.coalesce(Transaction.fee, 0),
                    )
                ).label("total_fees"),
            ).where(Transaction.asset_id == asset.id)
        )
        row = fee_result.one()
        total_fees = float(row[0] or 0)

        return (total_invested + total_fees) / qty

    # ------------------------------------------------------------------
    # Risk weight snapshot (current)
    # ------------------------------------------------------------------

    async def _get_current_risk_weight(self, db: AsyncSession, asset: Asset, user_id: str) -> Optional[float]:
        """Get current risk weight for an asset's symbol, caching for today."""
        today_str = date.today().isoformat()
        symbol_upper = asset.symbol.upper()

        # Check cache first
        cached = await self._get_cached_risk_weight(symbol_upper, today_str)
        if cached is not None:
            return cached

        # Compute via metrics_service for the asset's portfolio
        from app.services.metrics_service import metrics_service

        try:
            portfolio_data = await metrics_service.get_portfolio_metrics(db, str(asset.portfolio_id))
            # Cache all symbols' risk weights for today
            for am in portfolio_data.get("assets", []):
                rw = am.get("risk_weight", 0.0)
                await self._cache_risk_weight(am["symbol"], today_str, rw)

            # Return the target symbol
            for am in portfolio_data.get("assets", []):
                if am["symbol"].upper() == symbol_upper:
                    return am.get("risk_weight", 0.0)
        except Exception as e:
            logger.warning("Failed to compute risk weight for %s: %s", symbol_upper, e)

        return None

    # ------------------------------------------------------------------
    # Alert checking
    # ------------------------------------------------------------------

    async def check_alerts(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[AlertTrigger]:
        """Check all active alerts for a user and return triggered ones."""
        from app.models.user import User

        triggered = []

        # Fetch user for Telegram preferences
        user_result = await db.execute(select(User).where(User.id == user_id))
        user_obj = user_result.scalar_one_or_none()

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

                # Determine priority
                priority = (
                    NotificationPriority.URGENT
                    if alert.condition == AlertCondition.VOLATILITY_SPIKE
                    else NotificationPriority.HIGH
                )

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
                    priority=priority,
                )

                # Send Telegram alert (best-effort, per-user, with cooldown)
                try:
                    if user_obj and user_obj.telegram_enabled and user_obj.telegram_chat_id:
                        from app.services.telegram_service import telegram_service

                        tg_priority = "critical" if priority == NotificationPriority.URGENT else "high"
                        await telegram_service.send_smart_alert(
                            message=trigger.message,
                            chat_id=user_obj.telegram_chat_id,
                            user_id=str(user_obj.id),
                            priority=tg_priority,
                            symbol=trigger.symbol,
                            alert_type=trigger.condition,
                        )
                except Exception as e:
                    logger.debug("Telegram alert failed for %s: %s", trigger.symbol, e)

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
        result = await db.execute(select(Asset).where(Asset.id == alert.asset_id))
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
            daily_change = await self._get_daily_change(asset)
            if daily_change is not None and daily_change >= threshold:
                should_trigger = True
                message = f"{asset.symbol} hausse journalière de {daily_change:.1f}% (seuil: {threshold}%)"

        elif alert.condition == AlertCondition.DAILY_CHANGE_DOWN:
            daily_change = await self._get_daily_change(asset)
            if daily_change is not None and daily_change <= -threshold:
                should_trigger = True
                message = f"{asset.symbol} baisse journalière de {abs(daily_change):.1f}% (seuil: {threshold}%)"

        elif alert.condition == AlertCondition.TARGET_BREAK_EVEN:
            breakeven = await self._compute_breakeven_price(db, asset)
            if breakeven is not None and breakeven > 0 and current_price > breakeven:
                should_trigger = True
                threshold = breakeven
                message = (
                    f"\U0001f680 {asset.symbol} est redevenu rentable ! "
                    f"Prix actuel : {current_price:.2f}\u20ac "
                    f"(Break-even : {breakeven:.2f}\u20ac)"
                )

        elif alert.condition == AlertCondition.VOLATILITY_SPIKE:
            yesterday_str = (date.today() - timedelta(days=1)).isoformat()

            current_rw = await self._get_current_risk_weight(db, asset, str(alert.user_id))
            yesterday_rw = await self._get_cached_risk_weight(asset.symbol, yesterday_str)

            if current_rw is not None and yesterday_rw is not None and yesterday_rw > 0:
                rw_change_pct = (current_rw - yesterday_rw) / yesterday_rw * 100
                if rw_change_pct > 20:
                    # Correlate with anomaly detector (best-effort)
                    anomaly_info = ""
                    try:
                        from app.ml.anomaly_detector import AnomalyDetector
                        from app.models.asset_price_history import AssetPriceHistory

                        cutoff = (datetime.utcnow() - timedelta(days=30)).date()
                        hist_result = await db.execute(
                            select(AssetPriceHistory.price_eur)
                            .where(
                                AssetPriceHistory.symbol == asset.symbol.upper(),
                                AssetPriceHistory.price_date >= cutoff,
                            )
                            .order_by(AssetPriceHistory.price_date)
                        )
                        prices = [float(r[0]) for r in hist_result.all()]

                        if len(prices) >= 10:
                            detector = AnomalyDetector()
                            anomaly = detector.detect(
                                symbol=asset.symbol,
                                prices=prices,
                                current_price=current_price,
                                avg_buy_price=float(asset.avg_buy_price),
                                asset_type=asset.asset_type.value,
                            )
                            if anomaly and anomaly.is_anomaly:
                                anomaly_info = f" Anomalie confirmée: {anomaly.description}"
                    except Exception as e:
                        logger.debug("Anomaly correlation failed for %s: %s", asset.symbol, e)

                    should_trigger = True
                    threshold = rw_change_pct
                    message = (
                        f"\u26a0\ufe0f Pic de volatilité sur {asset.symbol} ! "
                        f"Contribution au risque: {current_rw:.1f}% "
                        f"(+{rw_change_pct:.0f}% en 24h).{anomaly_info}"
                    )

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

    async def _get_daily_change(self, asset: Asset) -> Optional[float]:
        """Get 24h price change percentage for an asset."""
        try:
            if asset.asset_type == AssetType.CRYPTO:
                prices = await self.price_service.get_multiple_crypto_prices([asset.symbol], "eur")
                data = prices.get(asset.symbol.upper())
                if data:
                    return float(data.get("change_percent_24h", 0) or 0)
            elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                data = await self.price_service.get_stock_price(asset.symbol)
                if data:
                    return float(data.get("change_percent_24h", 0) or 0)
        except Exception:
            pass
        return None

    async def _get_asset_price(self, asset: Asset) -> float:
        """Get current price for an asset."""
        try:
            if asset.asset_type == AssetType.CRYPTO:
                price = await self.price_service.get_crypto_price(asset.symbol)
                if isinstance(price, dict):
                    return float(price.get("price", 0) or price.get("eur", 0))
                return float(price) if price else float(asset.avg_buy_price)
            elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                data = await self.price_service.get_stock_price(asset.symbol)
                if isinstance(data, dict):
                    return float(data.get("price", 0))
                return float(data) if data else float(asset.avg_buy_price)
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
        result = await db.execute(select(Alert).where(Alert.user_id == user_id))
        alerts = result.scalars().all()

        active_count = sum(1 for a in alerts if a.is_active)
        triggered_today = sum(1 for a in alerts if a.triggered_at and a.triggered_at.date() == datetime.utcnow().date())
        total_triggered = sum(a.triggered_count or 0 for a in alerts)

        return {
            "total_alerts": len(alerts),
            "active_alerts": active_count,
            "triggered_today": triggered_today,
            "total_triggers": total_triggered,
        }


# Singleton instance
alert_service = AlertService()
