"""Historical price data fetcher for ML models."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np

from app.core.symbol_map import COINGECKO_SYMBOL_MAP

logger = logging.getLogger(__name__)

# Global semaphore: max 5 concurrent CoinGecko requests (~50 req/min free tier)
_coingecko_semaphore = asyncio.Semaphore(5)
# Minimum delay between CoinGecko calls (seconds)
_COINGECKO_MIN_DELAY = 1.2
_last_coingecko_call = 0.0
# Flag to remember if the API key is invalid (avoid wasting rate-limited slots)
_api_key_invalid = False


async def _coingecko_throttle():
    """Rate-limit CoinGecko calls with semaphore + minimum delay."""
    global _last_coingecko_call
    async with _coingecko_semaphore:
        now = asyncio.get_event_loop().time()
        elapsed = now - _last_coingecko_call
        if elapsed < _COINGECKO_MIN_DELAY:
            await asyncio.sleep(_COINGECKO_MIN_DELAY - elapsed)
        _last_coingecko_call = asyncio.get_event_loop().time()


@dataclass
class HistoricalDataResult:
    """Extended historical data with optional volume."""

    dates: List[datetime]
    prices: List[float]
    volumes: Optional[List[float]] = None


class HistoricalDataFetcher:
    """Fetches historical price data from CoinGecko and Yahoo Finance."""

    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    # Unified symbol map (single source of truth in app.core.symbol_map)
    SYMBOL_MAP: Dict[str, str] = COINGECKO_SYMBOL_MAP

    def __init__(self, coingecko_api_key: Optional[str] = None):
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        if coingecko_api_key and not _api_key_invalid:
            headers["x-cg-demo-api-key"] = coingecko_api_key

        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def _coingecko_get(
        self, url: str, params: dict, symbol: str, max_retries: int = 3, fast: bool = False
    ) -> Optional[dict]:
        """CoinGecko GET with rate-limiting, retry + exponential backoff."""
        for attempt in range(max_retries):
            await _coingecko_throttle()
            try:
                response = await self.http_client.get(url, params=params)
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 429:
                    wait = 2 if fast else (attempt + 1) * 10  # fast: 2s, normal: 10s, 20s, 30s
                    logger.warning("CoinGecko 429 for %s — retry %d/%d in %ds", symbol, attempt + 1, max_retries, wait)
                    await asyncio.sleep(wait)
                    continue
                if response.status_code == 401:
                    global _api_key_invalid
                    if not _api_key_invalid:
                        logger.warning("CoinGecko 401 for %s — API key invalid, retrying without key", symbol)
                        _api_key_invalid = True
                        self.http_client.headers.pop("x-cg-demo-api-key", None)
                        continue  # retry this attempt without the key
                    return None
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logger.warning("CoinGecko HTTP error for %s on attempt %d", symbol, attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
            except Exception as e:
                logger.warning("CoinGecko request failed for %s: %s", symbol, e)
                return None
        logger.warning("CoinGecko exhausted %d retries for %s", max_retries, symbol)
        return None

    async def get_crypto_history(
        self,
        symbol: str,
        days: int = 90,
        currency: str = "eur",
        fast: bool = False,
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical crypto prices from CoinGecko.

        Returns:
            Tuple of (dates, prices) lists.
        """
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

        data = await self._coingecko_get(
            f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
            {"vs_currency": currency, "days": str(days), "interval": "daily"},
            symbol,
            max_retries=1 if fast else 3,
            fast=fast,
        )
        if not data:
            return [], []

        prices_data = data.get("prices", [])
        if not prices_data:
            return [], []

        dates = [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).replace(tzinfo=None) for p in prices_data]
        prices = [p[1] for p in prices_data]

        logger.info("Fetched %d data points for %s from CoinGecko", len(prices), symbol)
        return dates, prices

    async def get_stock_history(
        self,
        symbol: str,
        days: int = 90,
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical stock/ETF prices from Yahoo Finance.

        Returns:
            Tuple of (dates, prices) lists.
        """
        try:
            # Yahoo range mapping
            if days <= 7:
                range_str = "5d"
            elif days <= 30:
                range_str = "1mo"
            elif days <= 90:
                range_str = "3mo"
            elif days <= 180:
                range_str = "6mo"
            elif days <= 365:
                range_str = "1y"
            elif days <= 730:
                range_str = "2y"
            else:
                range_str = "5y"

            response = await self.http_client.get(
                f"{self.YAHOO_BASE_URL}/{symbol}",
                params={
                    "interval": "1d",
                    "range": range_str,
                },
            )
            response.raise_for_status()
            data = response.json()

            chart = data.get("chart", {}).get("result", [{}])[0]
            timestamps = chart.get("timestamp", [])
            closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])

            if not timestamps or not closes:
                return [], []

            dates = [datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None) for ts in timestamps]
            prices = [float(c) for c in closes if c is not None]
            dates = dates[: len(prices)]

            logger.info("Fetched %d data points for %s from Yahoo Finance", len(prices), symbol)
            return dates, prices

        except Exception as e:
            logger.warning("Failed to fetch stock history for %s: %s", symbol, e)
            return [], []

    async def get_real_estate_history(
        self,
        symbol: str,
        days: int = 90,
        purchase_price: Optional[float] = None,
    ) -> Tuple[List[datetime], List[float]]:
        """Generate synthetic real estate historical prices.

        Physical real estate (France residential) has fundamentally different
        characteristics from REIT ETFs (~15% vol). We use a synthetic series
        calibrated to French residential: ~3% annual return, ~3% annual vol,
        with seasonal patterns. REIT proxies are NOT used because they
        completely distort risk metrics (VaR, correlation, Markowitz weights).
        """
        logger.info("Generating synthetic real estate history for %s", symbol)
        now = datetime.utcnow()
        # France residential real estate parameters
        annual_return = 0.03
        annual_vol = 0.03
        daily_return = annual_return / 365
        daily_vol = annual_vol / np.sqrt(365)

        rng = np.random.default_rng(hash(symbol) % (2**31))
        n = days
        daily_returns = rng.normal(daily_return, daily_vol, n)

        # Add seasonal pattern: slight dip in winter (Nov-Feb), recovery in spring
        for i in range(n):
            day_date = now - timedelta(days=n - i)
            month = day_date.month
            if month in (11, 12, 1, 2):
                daily_returns[i] -= 0.0001  # winter drag
            elif month in (3, 4, 5):
                daily_returns[i] += 0.00015  # spring recovery

        # Start at purchase price if available, else 100 index
        base_price = purchase_price if purchase_price and purchase_price > 0 else 100.0
        prices_arr = base_price * np.exp(np.cumsum(daily_returns))
        dates = [now - timedelta(days=n - i) for i in range(n)]
        prices = prices_arr.tolist()

        return dates, prices

    async def get_crypto_history_extended(
        self,
        symbol: str,
        days: int = 365,
        currency: str = "eur",
    ) -> HistoricalDataResult:
        """Fetch historical crypto prices + volumes from CoinGecko."""
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

        data = await self._coingecko_get(
            f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
            {"vs_currency": currency, "days": str(days), "interval": "daily"},
            symbol,
        )
        if not data:
            return HistoricalDataResult([], [], None)

        prices_data = data.get("prices", [])
        volumes_data = data.get("total_volumes", [])
        if not prices_data:
            return HistoricalDataResult([], [], None)

        dates = [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).replace(tzinfo=None) for p in prices_data]
        prices = [p[1] for p in prices_data]

        volumes = None
        if volumes_data and len(volumes_data) >= len(prices_data):
            volumes = [v[1] for v in volumes_data[: len(prices_data)]]

        logger.info("Fetched %d data points (with volume) for %s from CoinGecko", len(prices), symbol)
        return HistoricalDataResult(dates, prices, volumes)

    async def get_stock_history_extended(
        self,
        symbol: str,
        days: int = 365,
    ) -> HistoricalDataResult:
        """Fetch historical stock/ETF prices + volumes from Yahoo Finance."""
        try:
            if days <= 7:
                range_str = "5d"
            elif days <= 30:
                range_str = "1mo"
            elif days <= 90:
                range_str = "3mo"
            elif days <= 180:
                range_str = "6mo"
            elif days <= 365:
                range_str = "1y"
            elif days <= 730:
                range_str = "2y"
            else:
                range_str = "5y"

            response = await self.http_client.get(
                f"{self.YAHOO_BASE_URL}/{symbol}",
                params={"interval": "1d", "range": range_str},
            )
            response.raise_for_status()
            data = response.json()

            chart = data.get("chart", {}).get("result", [{}])[0]
            timestamps = chart.get("timestamp", [])
            quote = chart.get("indicators", {}).get("quote", [{}])[0]
            closes = quote.get("close", [])
            raw_volumes = quote.get("volume", [])

            if not timestamps or not closes:
                return HistoricalDataResult([], [], None)

            # Filter out None closes
            valid = [
                (ts, c, raw_volumes[i] if i < len(raw_volumes) else None)
                for i, (ts, c) in enumerate(zip(timestamps, closes))
                if c is not None
            ]
            if not valid:
                return HistoricalDataResult([], [], None)

            dates = [datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None) for ts, _, _ in valid]
            prices = [float(c) for _, c, _ in valid]
            volumes = [float(v) if v is not None else 0.0 for _, _, v in valid]

            logger.info("Fetched %d data points (with volume) for %s from Yahoo", len(prices), symbol)
            return HistoricalDataResult(dates, prices, volumes)

        except Exception as e:
            logger.warning("Failed to fetch extended stock history for %s: %s", symbol, e)
            return HistoricalDataResult([], [], None)

    async def get_history(
        self,
        symbol: str,
        asset_type: str,
        days: int = 90,
        fast: bool = False,
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical data for any asset type."""
        if asset_type == "crypto":
            return await self.get_crypto_history(symbol, days, fast=fast)
        elif asset_type in ("stock", "etf"):
            return await self.get_stock_history(symbol, days)
        elif asset_type == "real_estate":
            return await self.get_real_estate_history(symbol, days)
        return [], []

    async def get_history_extended(
        self,
        symbol: str,
        asset_type: str,
        days: int = 365,
    ) -> HistoricalDataResult:
        """Fetch historical data with volume for any asset type."""
        if asset_type == "crypto":
            return await self.get_crypto_history_extended(symbol, days)
        elif asset_type in ("stock", "etf"):
            return await self.get_stock_history_extended(symbol, days)
        elif asset_type == "real_estate":
            # Real estate has no volume — wrap existing method
            dates, prices = await self.get_real_estate_history(symbol, days)
            return HistoricalDataResult(dates, prices, None)
        return HistoricalDataResult([], [], None)

    async def get_crypto_history_range(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        currency: str = "eur",
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical crypto prices for a specific date range via CoinGecko /market_chart/range.

        This endpoint returns daily data for ranges > 90 days, which makes it
        ideal for deep backfill beyond the 365-day limit of /market_chart.
        """
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

        from_ts = int(from_date.timestamp())
        to_ts = int(to_date.timestamp())

        data = await self._coingecko_get(
            f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/market_chart/range",
            {"vs_currency": currency, "from": str(from_ts), "to": str(to_ts)},
            symbol,
        )
        if not data:
            return [], []

        prices_data = data.get("prices", [])
        if not prices_data:
            return [], []

        dates = [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).replace(tzinfo=None) for p in prices_data]
        prices = [p[1] for p in prices_data]

        logger.info(
            "Fetched %d data points for %s from CoinGecko /range (%s → %s)",
            len(prices),
            symbol,
            from_date.date(),
            to_date.date(),
        )
        return dates, prices

    async def get_coin_price_by_date(
        self,
        symbol: str,
        date: datetime,
        currency: str = "eur",
    ) -> Optional[float]:
        """Fetch the price of a coin on a specific historical date.

        Uses CoinGecko /coins/{id}/history?date={dd-mm-yyyy} endpoint.
        Available on free tier with NO date limit — works for any past date.
        Returns the price in the specified currency, or None on failure.
        """
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())
        date_str = date.strftime("%d-%m-%Y")

        data = await self._coingecko_get(
            f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/history",
            {"date": date_str, "localization": "false"},
            symbol,
        )
        if not data:
            return None

        try:
            price = data.get("market_data", {}).get("current_price", {}).get(currency)
            if price is not None:
                return float(price)
        except (KeyError, TypeError, ValueError):
            pass
        return None

    async def get_btc_dominance(self) -> Optional[float]:
        """Fetch BTC dominance percentage from CoinGecko /global."""
        data = await self._coingecko_get(f"{self.COINGECKO_BASE_URL}/global", {}, "BTC_DOMINANCE")
        if data:
            return data.get("data", {}).get("market_cap_percentage", {}).get("btc")
        return None
