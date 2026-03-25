"""Market data service for stocks/ETFs with market calendar awareness.

Provides:
- Stock/ETF price fetching via Yahoo Finance chart API
- Market calendar awareness (NYSE, Euronext, XETRA, LSE)
- Staleness detection that respects market hours
- Batch price fetching with concurrent requests
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

import httpx
from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class MarketExchange(str, Enum):
    """Known stock exchanges with their timezone and trading hours."""

    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    EURONEXT = "EURONEXT"
    XETRA = "XETRA"
    LSE = "LSE"
    TSX = "TSX"
    UNKNOWN = "UNKNOWN"


# Trading hours (local time) and UTC offsets for each exchange
# Format: (open_hour, open_min, close_hour, close_min, utc_offset_winter, utc_offset_summer)
_EXCHANGE_HOURS: Dict[MarketExchange, Tuple[int, int, int, int, int, int]] = {
    MarketExchange.NYSE: (9, 30, 16, 0, -5, -4),
    MarketExchange.NASDAQ: (9, 30, 16, 0, -5, -4),
    MarketExchange.EURONEXT: (9, 0, 17, 30, 1, 2),
    MarketExchange.XETRA: (9, 0, 17, 30, 1, 2),
    MarketExchange.LSE: (8, 0, 16, 30, 0, 1),
    MarketExchange.TSX: (9, 30, 16, 0, -5, -4),
}

# Weekend days (Saturday=5, Sunday=6)
_WEEKEND = {5, 6}

# Known market holidays (2026) — major US/EU holidays
# In production, this should be updated annually or fetched from an API
_MARKET_HOLIDAYS_2026 = {
    # US holidays (NYSE/NASDAQ closed)
    "NYSE": {
        "2026-01-01",  # New Year
        "2026-01-19",  # MLK Day
        "2026-02-16",  # Presidents Day
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-07-03",  # Independence Day (observed)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Christmas
    },
    # Euronext holidays
    "EURONEXT": {
        "2026-01-01",
        "2026-04-03",
        "2026-04-06",
        "2026-05-01",
        "2026-12-25",
        "2026-12-26",
    },
    "XETRA": {
        "2026-01-01",
        "2026-04-03",
        "2026-04-06",
        "2026-05-01",
        "2026-12-24",
        "2026-12-25",
        "2026-12-31",
    },
}
# Alias NASDAQ to NYSE holidays
_MARKET_HOLIDAYS_2026["NASDAQ"] = _MARKET_HOLIDAYS_2026["NYSE"]


def _detect_exchange(ticker: str) -> MarketExchange:
    """Detect the market exchange from a Yahoo Finance ticker suffix.

    Examples:
        AAPL -> NYSE (default US)
        MC.PA -> EURONEXT
        SAP.DE -> XETRA
        HSBA.L -> LSE
        RY.TO -> TSX
    """
    if "." not in ticker:
        return MarketExchange.NYSE  # Default: US stock

    suffix = ticker.rsplit(".", 1)[-1].upper()
    _suffix_map = {
        "PA": MarketExchange.EURONEXT,
        "AS": MarketExchange.EURONEXT,
        "BR": MarketExchange.EURONEXT,
        "LS": MarketExchange.EURONEXT,
        "MI": MarketExchange.EURONEXT,
        "DE": MarketExchange.XETRA,
        "L": MarketExchange.LSE,
        "TO": MarketExchange.TSX,
        "V": MarketExchange.TSX,
    }
    return _suffix_map.get(suffix, MarketExchange.UNKNOWN)


def _is_dst(dt: datetime, exchange: MarketExchange) -> bool:
    """Approximate DST check (US/EU rules).

    US: 2nd Sunday of March to 1st Sunday of November
    EU: Last Sunday of March to last Sunday of October
    """
    month = dt.month
    if exchange in (MarketExchange.NYSE, MarketExchange.NASDAQ, MarketExchange.TSX):
        # US DST: roughly March 8-14 to November 1-7
        if month > 3 and month < 11:
            return True
        if month == 3 and dt.day >= 8:
            return True
        if month == 11 and dt.day < 7:
            return True
        return False
    else:
        # EU DST: roughly last week of March to last week of October
        if month > 3 and month < 10:
            return True
        if month == 3 and dt.day >= 25:
            return True
        if month == 10 and dt.day >= 25:
            return False
        if month == 10:
            return True
        return False


def is_market_open(ticker: str, dt: Optional[datetime] = None) -> bool:
    """Check if the market for a given ticker is currently open.

    Args:
        ticker: Yahoo Finance ticker (e.g. "AAPL", "MC.PA")
        dt: Datetime to check (UTC). Defaults to now.

    Returns:
        True if the market is open at the given time.
    """
    if dt is None:
        dt = datetime.utcnow()

    exchange = _detect_exchange(ticker)
    hours = _EXCHANGE_HOURS.get(exchange)
    if not hours:
        return True  # Unknown exchange — assume open

    open_h, open_m, close_h, close_m, offset_winter, offset_summer = hours

    # Check weekend
    if dt.weekday() in _WEEKEND:
        return False

    # Check holidays
    date_str = dt.strftime("%Y-%m-%d")
    holidays = _MARKET_HOLIDAYS_2026.get(exchange.value, set())
    if date_str in holidays:
        return False

    # Convert UTC to local exchange time
    dst = _is_dst(dt, exchange)
    offset = offset_summer if dst else offset_winter
    local_dt = dt + timedelta(hours=offset)

    local_time = local_dt.time()
    market_open = time(open_h, open_m)
    market_close = time(close_h, close_m)

    return market_open <= local_time <= market_close


def is_market_closed_today(ticker: str, dt: Optional[datetime] = None) -> bool:
    """Check if the market is closed for the entire day (weekend or holiday).

    Different from is_market_open: returns True on weekends/holidays
    regardless of time. Used to avoid marking prices as stale.
    """
    if dt is None:
        dt = datetime.utcnow()

    if dt.weekday() in _WEEKEND:
        return True

    exchange = _detect_exchange(ticker)
    date_str = dt.strftime("%Y-%m-%d")
    holidays = _MARKET_HOLIDAYS_2026.get(exchange.value, set())
    return date_str in holidays


def price_staleness_hours(ticker: str, last_update: datetime) -> Tuple[float, bool]:
    """Compute effective staleness in trading hours, respecting market calendar.

    Returns:
        (staleness_hours, is_acceptable): staleness in hours and whether
        the price is considered acceptably fresh given market hours.
    """
    now = datetime.utcnow()
    raw_age_hours = (now - last_update).total_seconds() / 3600

    # If market is currently closed for the day, price from last trading
    # session is acceptable (up to 72h for long weekends)
    if is_market_closed_today(ticker, now):
        return raw_age_hours, raw_age_hours < 72

    # During market hours, staleness > 15 min is not acceptable
    # Outside market hours (same day), staleness up to 18h is fine
    if is_market_open(ticker, now):
        return raw_age_hours, raw_age_hours < 0.25  # 15 minutes
    else:
        return raw_age_hours, raw_age_hours < 18


class MarketDataService:
    """Service for fetching and caching stock/ETF market data."""

    YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    CACHE_TTL_STOCK = 300  # 5 minutes
    CACHE_TTL_CLOSED = 3600  # 1 hour when market is closed

    def __init__(self):
        self.redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
        self.http_client = httpx.AsyncClient(
            timeout=5.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    def _cache_key(self, ticker: str) -> str:
        return f"mkt:stock:{ticker.upper()}"

    def _get_cached(self, ticker: str) -> Optional[Dict]:
        """Get cached stock price data."""
        try:
            key = self._cache_key(ticker)
            data = self.redis.hgetall(key)
            if not data or "price" not in data:
                return None

            # Check freshness
            last_updated = data.get("last_updated")
            if last_updated:
                try:
                    last_dt = datetime.fromisoformat(last_updated)
                    _, acceptable = price_staleness_hours(ticker, last_dt)
                    if not acceptable:
                        return None
                except (ValueError, TypeError):
                    pass

            return {
                "price": Decimal(data["price"]),
                "change_24h": float(data.get("change_24h", 0)),
                "change_percent_24h": float(data.get("change_percent_24h", 0)),
                "volume": float(data.get("volume", 0)),
                "quote_currency": data.get("quote_currency", "USD"),
                "exchange": data.get("exchange", ""),
                "last_updated": last_updated,
            }
        except Exception as e:
            logger.warning("Cache read error for %s: %s", ticker, e)
        return None

    def _cache_set(self, ticker: str, data: Dict):
        """Cache stock price data with market-aware TTL."""
        try:
            key = self._cache_key(ticker)
            ttl = self.CACHE_TTL_CLOSED if is_market_closed_today(ticker) else self.CACHE_TTL_STOCK
            cache_data = {
                "price": str(data["price"]),
                "change_24h": str(data.get("change_24h", 0)),
                "change_percent_24h": str(data.get("change_percent_24h", 0)),
                "volume": str(data.get("volume", 0)),
                "quote_currency": data.get("quote_currency", "USD"),
                "exchange": data.get("exchange", ""),
                "last_updated": datetime.utcnow().isoformat(),
            }
            self.redis.hset(key, mapping=cache_data)
            self.redis.expire(key, ttl)
        except Exception as e:
            logger.warning("Cache write error for %s: %s", ticker, e)

    async def get_stock_price(self, ticker: str) -> Optional[Dict]:
        """Fetch stock/ETF price from Yahoo Finance with caching.

        Returns dict with: price, change_24h, change_percent_24h,
        volume, quote_currency, exchange.
        """
        # Check cache first
        cached = self._get_cached(ticker)
        if cached:
            return cached

        try:
            response = await self.http_client.get(
                f"{self.YAHOO_BASE_URL}/{ticker}",
                params={"interval": "1d", "range": "5d"},
            )
            response.raise_for_status()
            data = response.json()

            chart = data.get("chart", {}).get("result", [{}])[0]
            meta = chart.get("meta", {})

            current_price = meta.get("regularMarketPrice", 0)
            if not current_price:
                return None

            previous_close = meta.get("previousClose", current_price)
            quote_currency = meta.get("currency", "USD").upper()
            exchange_name = meta.get("exchangeName", "")

            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close else 0

            result = {
                "price": Decimal(str(current_price)),
                "change_24h": round(change, 4),
                "change_percent_24h": round(change_percent, 2),
                "volume": meta.get("regularMarketVolume", 0),
                "quote_currency": quote_currency,
                "exchange": exchange_name,
            }
            self._cache_set(ticker, result)
            return result

        except Exception as e:
            logger.error("Error fetching stock price for %s: %s", ticker, e)
            return None

    async def get_multiple_stock_prices(self, tickers: List[str], max_concurrent: int = 10) -> Dict[str, Dict]:
        """Fetch multiple stock prices concurrently.

        Args:
            tickers: List of Yahoo Finance tickers
            max_concurrent: Max concurrent requests

        Returns:
            Dict mapping ticker -> price data
        """
        results: Dict[str, Dict] = {}

        # Check cache first
        uncached = []
        for ticker in tickers:
            cached = self._get_cached(ticker)
            if cached:
                results[ticker.upper()] = cached
            else:
                uncached.append(ticker)

        if not uncached:
            return results

        # Fetch uncached in batches
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _fetch(t: str):
            async with semaphore:
                return t, await self.get_stock_price(t)

        tasks = [_fetch(t) for t in uncached]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        for item in fetched:
            if isinstance(item, Exception):
                continue
            ticker, data = item
            if data:
                results[ticker.upper()] = data

        return results

    async def get_stock_price_eur(self, ticker: str, forex_rate_fn=None) -> Optional[Dict]:
        """Fetch stock price and convert to EUR.

        Args:
            ticker: Yahoo Finance ticker
            forex_rate_fn: Async callable(from_ccy, to_ccy) -> Decimal
                           If None, returns price in quote currency.

        Returns:
            Price data with price_eur field added.
        """
        data = await self.get_stock_price(ticker)
        if not data:
            return None

        quote_ccy = data["quote_currency"]
        if quote_ccy == "EUR":
            data["price_eur"] = data["price"]
            return data

        if forex_rate_fn:
            try:
                rate = await forex_rate_fn(quote_ccy, "EUR")
                if rate:
                    data["price_eur"] = data["price"] * Decimal(str(rate))
                    return data
            except Exception:
                logger.warning("Forex conversion %s→EUR failed for %s", quote_ccy, ticker)

        # Fallback: mark as unconverted
        data["price_eur"] = None
        return data

    def get_staleness_info(self, ticker: str, last_update: datetime) -> Dict:
        """Get human-readable staleness information for a stock price.

        Returns dict with:
            age_hours: float
            is_fresh: bool
            reason: str (e.g. "market closed", "within trading hours")
        """
        age_hours, acceptable = price_staleness_hours(ticker, last_update)

        if is_market_closed_today(ticker):
            reason = "market closed (weekend/holiday)"
        elif is_market_open(ticker):
            reason = "market open"
        else:
            reason = "market closed (after hours)"

        return {
            "age_hours": round(age_hours, 1),
            "is_fresh": acceptable,
            "reason": reason,
        }


# Singleton instance
market_data_service = MarketDataService()
