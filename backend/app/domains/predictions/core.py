import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.ml.anomaly_detector import AnomalyDetector
from app.ml.forecaster import PriceForecaster
from app.ml.regime_detector import MarketRegimeDetector


async def user_portfolio_ids(db: AsyncSession, user_id: str) -> list[uuid.UUID]:
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    return [p.id for p in result.scalars().all()]


async def held_assets(db: AsyncSession, portfolio_ids: list[uuid.UUID]) -> Sequence[Asset]:
    result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids), Asset.quantity > 0))
    return result.scalars().all()


class PredictionCore:
    def __init__(self) -> None:
        self.forecaster = PriceForecaster()
        self.anomaly_detector = AnomalyDetector()  # type: ignore[no-untyped-call]
        self.regime_detector = MarketRegimeDetector()

    async def _get_current_price(self, symbol: str, asset_type: AssetType) -> float | None:
        quote = await price_feed.quote(symbol, asset_type)
        return float(quote.price) if quote is not None else None
