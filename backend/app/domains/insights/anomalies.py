"""Anomalies de cours et leur effet en euros sur les positions."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.insights import repository
from app.domains.insights.results import AnomalyImpact
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import AssetType
from app.domains.predictions.service import prediction_service
from app.domains.predictions.types import AnomalyDetection

logger = logging.getLogger(__name__)

_PRICE_DAYS = 7


@dataclass
class _Position:
    quantity: float
    average_price: float


async def _positions(db: AsyncSession, user_id: str) -> dict[str, _Position]:
    ids = await repository.portfolio_ids(db, user_id)
    assets = await repository.assets_of_portfolios(db, ids) if ids else {}
    positions: dict[str, _Position] = {}
    for asset in assets.values():
        if asset.asset_type == AssetType.CROWDFUNDING:
            continue
        if asset.symbol in positions:
            positions[asset.symbol].quantity += float(asset.quantity)
        else:
            positions[asset.symbol] = _Position(float(asset.quantity), float(asset.avg_buy_price))
    return positions


async def _current_price(symbol: str, position: _Position | None) -> float:
    fallback = position.average_price if position else 0
    try:
        prices = (await local_series(symbol, _PRICE_DAYS)).prices
        if prices:
            return prices[-1]
        quote = await price_feed.quote(symbol, "crypto") or await price_feed.quote(symbol, "stock")
        return float(quote.price) if quote is not None else fallback
    except Exception:
        logger.warning(
            "Cours indisponible pour %s — impact d'anomalie valorisé au prix de revient", symbol, exc_info=True
        )
        return fallback


async def _impact(anomaly: AnomalyDetection, positions: dict[str, _Position]) -> AnomalyImpact:
    position = positions.get(anomaly.symbol)
    price = await _current_price(anomaly.symbol, position)
    value = (position.quantity if position else 0) * (price or 0)
    return AnomalyImpact(
        symbol=anomaly.symbol,
        anomaly_type=anomaly.anomaly_type or "unknown",
        severity=anomaly.severity,
        description=anomaly.description,
        price_change_percent=anomaly.price_change_percent,
        position_value_eur=value,
        impact_eur=value * (anomaly.price_change_percent / 100),
        detected_at=anomaly.detected_at,
    )


async def anomaly_impacts(db: AsyncSession, user_id: str) -> list[AnomalyImpact]:
    """Anomalies détectées, la plus coûteuse ou la plus profitable en tête ; aucune si la détection échoue."""
    try:
        anomalies = await prediction_service.detect_anomalies(db, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to detect anomalies: %s", exc)
        return []
    positions = await _positions(db, user_id)
    impacts = [await _impact(anomaly, positions) for anomaly in anomalies if anomaly.is_anomaly]
    impacts.sort(key=lambda impact: abs(impact.impact_eur), reverse=True)
    return impacts
