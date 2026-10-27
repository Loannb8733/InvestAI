import json
import logging
from datetime import date
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_async_url, redis_client_kwargs
from app.domains.portfolio.models import Asset
from app.services.metrics_service import metrics_service

logger = logging.getLogger(__name__)

TTL_SECONDS = 172800


class RiskWeights:
    """Contribution au risque de chaque actif, mise en cache par jour pour comparer à la veille."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs())
        return self._redis

    async def store(self, symbol: str, day: str, risk_weight: float) -> None:
        """Enregistre la contribution au risque du symbole pour le jour donné (« YYYY-MM-DD »), 48 h."""
        try:
            key = f"riskweight:{symbol.upper()}:{day}"
            await self._client().setex(key, TTL_SECONDS, json.dumps({"risk_weight": risk_weight}))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to cache risk weight for %s: %s", symbol, exc)

    async def stored(self, symbol: str, day: str) -> float | None:
        """Contribution au risque enregistrée pour ce jour, None si absente."""
        try:
            data = await self._client().get(f"riskweight:{symbol.upper()}:{day}")
            if data:
                value: float | None = json.loads(data).get("risk_weight")
                return value
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis miss for risk weight %s: %s", symbol, exc)
        return None

    async def store_portfolio(self, db: AsyncSession, portfolio_id: str, day: str) -> list[dict[str, Any]]:
        """Calcule et enregistre la contribution au risque de chaque actif du portefeuille ; rend ses actifs."""
        portfolio = await metrics_service.get_portfolio_metrics(db, portfolio_id)
        assets: list[dict[str, Any]] = portfolio.get("assets", [])
        for metrics in assets:
            await self.store(metrics["symbol"], day, metrics.get("risk_weight", 0.0))
        return assets

    async def current(self, db: AsyncSession, asset: Asset) -> float | None:
        """Contribution au risque du jour, calculée sur le portefeuille de l'actif quand elle n'est pas en cache."""
        today = date.today().isoformat()
        symbol = asset.symbol.upper()
        cached = await self.stored(symbol, today)
        if cached is not None:
            return cached
        try:
            for metrics in await self.store_portfolio(db, str(asset.portfolio_id), today):
                if metrics["symbol"].upper() == symbol:
                    weight: float = metrics.get("risk_weight", 0.0)
                    return weight
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to compute risk weight for %s: %s", symbol, exc)
        return None


risk_weights = RiskWeights()
