import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domains.market_data.coingecko_api import BASE_URL, coingecko_headers
from app.domains.market_data.history.series import PriceSeries
from app.domains.market_data.prices.service import price_feed

logger = logging.getLogger(__name__)

TIMEOUT_S = 30.0
MIN_SPACING_S = 1.2
ATTEMPTS = 3
MAX_WAIT_S = 60.0


def _day(milliseconds: float) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).replace(tzinfo=None)


def _series(data: dict[str, Any]) -> PriceSeries:
    points = data.get("prices") or []
    volumes = data.get("total_volumes") or []
    return PriceSeries(
        dates=[_day(p[0]) for p in points],
        prices=[float(p[1]) for p in points],
        volumes=[float(v[1]) for v in volumes[: len(points)]] if len(volumes) >= len(points) and points else None,
    )


class CoinGeckoHistory:
    """Historique CoinGecko pour les tâches de fond : un appel à la fois, espacés, 429 respectés."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=TIMEOUT_S, headers=coingecko_headers())
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        for attempt in range(1, ATTEMPTS + 1):
            async with self._lock:
                wait = MIN_SPACING_S - (time.monotonic() - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_call = time.monotonic()
                try:
                    response = await self._client.get(f"{BASE_URL}{path}", params=params)
                except httpx.HTTPError as exc:
                    logger.warning("CoinGecko injoignable (%s) : %s", path, exc)
                    return None
            if response.status_code == 429 and attempt < ATTEMPTS:
                retry_after = float(response.headers.get("Retry-After") or 2 * attempt)
                logger.warning("CoinGecko 429 (%s), nouvel essai %d dans %.0f s", path, attempt + 1, retry_after)
                await asyncio.sleep(min(retry_after, MAX_WAIT_S))
                continue
            if response.status_code != 200:
                logger.warning("CoinGecko %d pour %s", response.status_code, path)
                return None
            return response.json()
        return None

    async def daily(self, symbol: str, days: int) -> PriceSeries:
        """Clôtures quotidiennes en EUR et volumes sur ``days`` jours (365 au plus en offre gratuite)."""
        coin = await price_feed.coingecko_id(symbol)
        if coin is None:
            return PriceSeries()
        data = await self._get(
            f"/coins/{coin}/market_chart", {"vs_currency": "eur", "days": str(days), "interval": "daily"}
        )
        return _series(data) if data else PriceSeries()

    async def between(self, symbol: str, start: datetime, end: datetime) -> PriceSeries:
        """Cours en EUR entre deux instants."""
        coin = await price_feed.coingecko_id(symbol)
        if coin is None:
            return PriceSeries()
        params = {"vs_currency": "eur", "from": str(int(start.timestamp())), "to": str(int(end.timestamp()))}
        data = await self._get(f"/coins/{coin}/market_chart/range", params)
        return _series(data) if data else PriceSeries()
