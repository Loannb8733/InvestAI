import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.alerts.models import Alert, AlertCondition
from app.domains.alerts.pricing import breakeven_price, daily_change
from app.domains.alerts.risk_weights import risk_weights
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset
from app.ml.anomaly_detector import AnomalyDetector

logger = logging.getLogger(__name__)

Outcome = tuple[float, str] | None
Rule = Callable[[AsyncSession, Alert, Asset, float], Awaitable[Outcome]]

SPIKE_PERCENT = 20
ANOMALY_WINDOW_DAYS = 30
ANOMALY_MIN_PRICES = 10


async def _price_above(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    if price > threshold:
        return threshold, f"{asset.symbol} a dépassé {threshold} {alert.currency} (actuel: {price:.2f})"
    return None


async def _price_below(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    if price < threshold:
        return threshold, f"{asset.symbol} est passé sous {threshold} {alert.currency} (actuel: {price:.2f})"
    return None


def _change(asset: Asset, price: float) -> float | None:
    average = float(asset.avg_buy_price)
    return (price - average) / average * 100 if average > 0 else None


async def _change_up(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    change = _change(asset, price)
    if change is not None and change >= threshold:
        return threshold, f"{asset.symbol} a augmenté de {change:.1f}% (seuil: {threshold}%)"
    return None


async def _change_down(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    change = _change(asset, price)
    if change is not None and change <= -threshold:
        return threshold, f"{asset.symbol} a baissé de {abs(change):.1f}% (seuil: {threshold}%)"
    return None


async def _daily_up(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    change = await daily_change(asset)
    if change is not None and change >= threshold:
        return threshold, f"{asset.symbol} hausse journalière de {change:.1f}% (seuil: {threshold}%)"
    return None


async def _daily_down(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    threshold = float(alert.threshold)
    change = await daily_change(asset)
    if change is not None and change <= -threshold:
        return threshold, f"{asset.symbol} baisse journalière de {abs(change):.1f}% (seuil: {threshold}%)"
    return None


async def _break_even(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    breakeven = await breakeven_price(db, asset)
    if breakeven is not None and breakeven > 0 and price > breakeven:
        return breakeven, (
            f"\U0001f680 {asset.symbol} est redevenu rentable ! "
            f"Prix actuel : {price:.2f}€ (Break-even : {breakeven:.2f}€)"
        )
    return None


async def _anomaly_note(db: AsyncSession, asset: Asset, price: float) -> str:
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=ANOMALY_WINDOW_DAYS)).date()
        rows = await db.execute(
            select(AssetPriceHistory.price_eur)
            .where(AssetPriceHistory.symbol == asset.symbol.upper(), AssetPriceHistory.price_date >= cutoff)
            .order_by(AssetPriceHistory.price_date)
        )
        prices = [float(row[0]) for row in rows.all()]
        if len(prices) >= ANOMALY_MIN_PRICES:
            anomaly = AnomalyDetector().detect(  # type: ignore[no-untyped-call]
                symbol=asset.symbol,
                prices=prices,
                current_price=price,
                avg_buy_price=float(asset.avg_buy_price),
                asset_type=asset.asset_type.value,
            )
            if anomaly and anomaly.is_anomaly:
                return f" Anomalie confirmée: {anomaly.description}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Anomaly correlation failed for %s: %s", asset.symbol, exc)
    return ""


async def _volatility(db: AsyncSession, alert: Alert, asset: Asset, price: float) -> Outcome:
    current = await risk_weights.current(db, asset)
    yesterday = await risk_weights.stored(asset.symbol, (date.today() - timedelta(days=1)).isoformat())
    if current is None or yesterday is None or yesterday <= 0:
        return None
    change = (current - yesterday) / yesterday * 100
    if change <= SPIKE_PERCENT:
        return None
    note = await _anomaly_note(db, asset, price)
    return change, (
        f"⚠️ Pic de volatilité sur {asset.symbol} ! "
        f"Contribution au risque: {current:.1f}% (+{change:.0f}% en 24h).{note}"
    )


RULES: dict[AlertCondition, Rule] = {
    AlertCondition.PRICE_ABOVE: _price_above,
    AlertCondition.PRICE_BELOW: _price_below,
    AlertCondition.CHANGE_PERCENT_UP: _change_up,
    AlertCondition.CHANGE_PERCENT_DOWN: _change_down,
    AlertCondition.DAILY_CHANGE_UP: _daily_up,
    AlertCondition.DAILY_CHANGE_DOWN: _daily_down,
    AlertCondition.TARGET_BREAK_EVEN: _break_even,
    AlertCondition.VOLATILITY_SPIKE: _volatility,
}
