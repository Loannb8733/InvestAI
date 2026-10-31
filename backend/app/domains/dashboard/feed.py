"""Blocs d'actualité du tableau de bord : transactions récentes, alertes, échéances, indices."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframe import get_period_start_date
from app.domains.dashboard import repository
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.schemas import ActiveAlert, IndexComparison, RecentTransaction, UpcomingEvent
from app.domains.market_data.prices.service import price_feed

logger = logging.getLogger(__name__)

_FEED_LIMIT = 5
_QUOTE_TIMEOUT = 5.0
_INDEX_SYMBOLS = (("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana"))


async def recent_transactions(
    db: AsyncSession, user_id: UUID, limit: int = _FEED_LIMIT, days: int = 0
) -> list[RecentTransaction]:
    """Dernières transactions, limitées à `days` jours si `days` est positif."""
    assets = {asset.id: asset for asset in await repository.user_assets(db, user_id)}
    if not assets:
        return []
    since = get_period_start_date(days) if days > 0 else None
    transactions = await repository.latest_transactions(db, list(assets), limit, since)
    feed = []
    for tx in transactions:
        asset = assets.get(tx.asset_id)
        price = float(tx.price)
        feed.append(
            RecentTransaction(
                id=str(tx.id),
                symbol=asset.symbol if asset else "N/A",
                asset_type=asset.asset_type.value if asset else "unknown",
                transaction_type=tx.transaction_type.value,
                quantity=float(tx.quantity),
                price=price,
                total=float(tx.quantity) * price,
                executed_at=(tx.executed_at or tx.created_at or datetime.now(UTC)).isoformat(),
            )
        )
    return feed


async def _alert_prices(symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {}
    try:
        quotes = await asyncio.wait_for(price_feed.crypto(symbols), timeout=_QUOTE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Alert price batch fetch failed: %s", exc)
        return {}
    return {symbol: quote.price for symbol, quote in quotes.items()}


async def active_alerts(db: AsyncSession, user_id: UUID) -> list[ActiveAlert]:
    """Alertes actives, avec le cours de leur actif quand il est disponible."""
    alerts = await repository.active_alerts(db, user_id, _FEED_LIMIT)
    asset_ids = [alert.asset_id for alert in alerts if alert.asset_id]
    assets = await repository.assets_by_id(db, asset_ids) if asset_ids else {}
    prices = await _alert_prices(list({asset.symbol for asset in assets.values()}))
    feed = []
    for alert in alerts:
        asset = assets.get(alert.asset_id) if alert.asset_id else None
        feed.append(
            ActiveAlert(
                id=str(alert.id),
                name=alert.name,
                symbol=asset.symbol if asset else None,
                condition=alert.condition.value,
                threshold=float(alert.threshold),
                current_price=prices.get(asset.symbol.upper()) if asset else None,
            )
        )
    return feed


async def upcoming_events(db: AsyncSession, user_id: UUID, days: int = 30) -> list[UpcomingEvent]:
    """Échéances des `days` prochains jours."""
    now = datetime.now(UTC)
    events = await repository.upcoming_events(db, user_id, now, now + timedelta(days=days), _FEED_LIMIT)
    return [
        UpcomingEvent(
            id=str(event.id),
            title=event.title,
            event_type=event.event_type.value,
            event_date=event.event_date.isoformat(),
            amount=float(event.amount) if event.amount else None,
        )
        for event in events
    ]


async def get_index_comparison(days: int = 30) -> list[IndexComparison]:
    """Variation de Bitcoin, Ethereum et Solana sur la période ; vide si les cours manquent."""
    symbols = [symbol for symbol, _ in _INDEX_SYMBOLS]
    indices: list[IndexComparison] = []
    try:
        quotes = await asyncio.wait_for(price_feed.crypto(symbols), timeout=_QUOTE_TIMEOUT)
        changes = await asyncio.wait_for(
            metrics_service.fetch_period_changes({"crypto": symbols}, days), timeout=_QUOTE_TIMEOUT
        )
        for symbol, name in _INDEX_SYMBOLS:
            if symbol in quotes:
                quote = quotes[symbol]
                change = changes.get(symbol, quote.change_percent_24h)
                indices.append(
                    IndexComparison(name=name, symbol=symbol, change_percent=change, price=float(quote.price))
                )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Index comparison fetch failed: %s", exc)
    return indices
