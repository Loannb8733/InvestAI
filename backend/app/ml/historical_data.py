"""Historical price data fetcher for ML models."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np

logger = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """Fetches historical price data from CoinGecko and Yahoo Finance."""

    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    # Common symbol -> CoinGecko ID mapping (subset, full map in PriceService)
    SYMBOL_MAP: Dict[str, str] = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "DOT": "polkadot", "LINK": "chainlink",
        "AVAX": "avalanche-2", "MATIC": "matic-network", "UNI": "uniswap",
        "ATOM": "cosmos", "LTC": "litecoin", "SHIB": "shiba-inu",
        "NEAR": "near", "SUI": "sui", "PEPE": "pepe",
        "PAXG": "pax-gold", "USDG": "first-digital-usd", "USDC": "usd-coin",
        "TAO": "bittensor", "USDT": "tether", "TON": "the-open-network",
        "FET": "fetch-ai",
    }

    def __init__(self, coingecko_api_key: Optional[str] = None):
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        if coingecko_api_key:
            headers["x-cg-demo-api-key"] = coingecko_api_key

        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def get_crypto_history(
        self,
        symbol: str,
        days: int = 90,
        currency: str = "eur",
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical crypto prices from CoinGecko.

        Returns:
            Tuple of (dates, prices) lists.
        """
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

        try:
            response = await self.http_client.get(
                f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
                params={
                    "vs_currency": currency,
                    "days": str(days),
                    "interval": "daily",
                },
            )
            if response.status_code == 429:
                logger.warning("CoinGecko 429 for %s — skipping (will retry on next page load)", symbol)
                return [], []
            response.raise_for_status()
            data = response.json()

            prices_data = data.get("prices", [])
            if not prices_data:
                return [], []

            dates = [datetime.fromtimestamp(p[0] / 1000) for p in prices_data]
            prices = [p[1] for p in prices_data]

            logger.info("Fetched %d data points for %s from CoinGecko", len(prices), symbol)
            return dates, prices

        except Exception as e:
            logger.warning("Failed to fetch crypto history for %s: %s", symbol, e)
            return [], []

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
            else:
                range_str = "1y"

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

            dates = [datetime.fromtimestamp(ts) for ts in timestamps]
            prices = [float(c) for c in closes if c is not None]
            dates = dates[:len(prices)]

            logger.info("Fetched %d data points for %s from Yahoo Finance", len(prices), symbol)
            return dates, prices

        except Exception as e:
            logger.warning("Failed to fetch stock history for %s: %s", symbol, e)
            return [], []

    async def get_real_estate_history(
        self,
        symbol: str,
        days: int = 90,
    ) -> Tuple[List[datetime], List[float]]:
        """Generate real estate historical prices.

        Strategy:
        1. Try EPRA Eurozone REIT ETF (IPRP.AS or EPRE.PA) as a proxy for
           European real estate market movements.
        2. Fallback: synthetic series with low volatility (~2-4% annualized)
           and slight upward drift matching long-term real estate trends.
        """
        # Try European REIT ETF as proxy
        for proxy_ticker in ["EPRE.PA", "IPRP.AS", "VNQ"]:
            try:
                dates, prices = await self.get_stock_history(proxy_ticker, days)
                if dates and len(dates) >= 5:
                    logger.info(
                        "Using %s as real estate proxy for %s (%d points)",
                        proxy_ticker, symbol, len(dates),
                    )
                    return dates, prices
            except Exception:
                continue

        # Fallback: synthetic series
        logger.info("Generating synthetic real estate history for %s", symbol)
        now = datetime.utcnow()
        # Real estate: ~3% annual return, ~4% annual volatility
        annual_return = 0.03
        annual_vol = 0.04
        daily_return = annual_return / 365
        daily_vol = annual_vol / np.sqrt(365)

        rng = np.random.default_rng(hash(symbol) % (2**31))
        n = days
        daily_returns = rng.normal(daily_return, daily_vol, n)
        # Start at 100 (index base)
        prices_arr = 100.0 * np.exp(np.cumsum(daily_returns))
        dates = [now - timedelta(days=n - i) for i in range(n)]
        prices = prices_arr.tolist()

        return dates, prices

    async def get_history(
        self,
        symbol: str,
        asset_type: str,
        days: int = 90,
    ) -> Tuple[List[datetime], List[float]]:
        """Fetch historical data for any asset type."""
        if asset_type == "crypto":
            return await self.get_crypto_history(symbol, days)
        elif asset_type in ("stock", "etf"):
            return await self.get_stock_history(symbol, days)
        elif asset_type == "real_estate":
            return await self.get_real_estate_history(symbol, days)
        return [], []
