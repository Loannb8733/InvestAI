import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.notifications.telegram.client import telegram_service
from app.domains.portfolio.models import Asset, Portfolio

logger = logging.getLogger(__name__)

BOTTOM_CONFIDENCE = 0.80
BOTTOM_DISTANCE_PCT = 5.0


async def _holders(db: AsyncSession, symbol: str) -> Sequence[User]:
    result = await db.execute(
        select(User)
        .join(Portfolio, Portfolio.user_id == User.id)
        .join(Asset, Asset.portfolio_id == Portfolio.id)
        .where(
            Asset.symbol == symbol,
            Asset.quantity > 0,
            User.telegram_enabled.is_(True),
            User.telegram_chat_id.isnot(None),
        )
        .distinct()
    )
    return result.scalars().all()


async def bottom_zone_alerts(
    db: AsyncSession, symbol: str, current_price: float, bottom: dict[str, Any]
) -> AsyncIterator[None]:
    """Alerte Telegram chaque détenteur quand le creux estimé est à moins de 5 % avec plus de 80 % de confiance ;
    rend la main une fois par alerte envoyée."""
    confidence = bottom.get("confidence", 0)
    distance_pct = abs(bottom.get("distance_pct", 100))
    if not (confidence > BOTTOM_CONFIDENCE and distance_pct < BOTTOM_DISTANCE_PCT):
        return

    for holder in await _holders(db, symbol):
        sent = await telegram_service.alert_bottom_zone(
            symbol=symbol,
            current_price=current_price,
            estimated_bottom=bottom.get("estimated_price", 0),
            confidence=confidence,
            distance_pct=distance_pct,
            chat_id=holder.telegram_chat_id or "",
            user_id=str(holder.id),
        )
        if sent:
            yield
            logger.info(
                "Bottom zone alert sent for %s to user %s (conf=%.0f%%, dist=%.1f%%)",
                symbol,
                holder.id,
                confidence * 100,
                distance_pct,
            )
