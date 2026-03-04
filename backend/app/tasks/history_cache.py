"""Task to pre-fetch and cache historical price data in Redis + PostgreSQL.

This avoids CoinGecko 429 errors on the Analytics page by fetching
historical data in the background with proper rate limiting.
PostgreSQL provides persistent storage; Redis is the fast-read layer.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset
from app.models.asset_price_history import AssetPriceHistory
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

REDIS_HISTORY_PREFIX = "hist:"
REDIS_HISTORY_TTL = 3600  # 1 hour
REDIS_HISTORY_FALLBACK_TTL = 86400  # 24 hours — stale-but-usable fallback
# Fetch 365 days by default so all timeframes (24h–1y) are served from one cache entry
DEFAULT_CACHE_DAYS = 365


def _get_redis() -> Redis:
    return Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)


def _run_async(coro):
    """Always create a fresh event loop to avoid 'attached to a different loop' errors."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _cache_key(symbol: str, days: int) -> str:
    """Build a Redis key that includes the period."""
    return f"{REDIS_HISTORY_PREFIX}{symbol.upper()}_{days}"


async def _get_all_crypto_symbols() -> list:
    """Get all unique crypto symbols from DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
        return [(row[0].upper(), row[1].value) for row in result.all()]


async def _persist_prices_to_db(symbol: str, dates: list, prices: list, source: str = "coingecko"):
    """Upsert price data into asset_price_history table.

    Deduplicates by (symbol, price_date) before inserting to avoid
    'ON CONFLICT DO UPDATE cannot affect row a second time' errors
    when CoinGecko returns duplicate dates at granularity boundaries.
    """
    if not dates or not prices:
        return
    try:
        async with AsyncSessionLocal() as db:
            # Deduplicate: keep last price for each date (most recent intraday value)
            seen: dict = {}
            for d, p in zip(dates, prices):
                price_date = d.date() if hasattr(d, "date") else d
                seen[(symbol.upper(), price_date)] = {
                    "symbol": symbol.upper(),
                    "price_date": price_date,
                    "price_eur": Decimal(str(p)),
                    "source": source,
                }
            rows = list(seen.values())

            # Batch upsert in chunks of 500 to avoid query size limits
            CHUNK_SIZE = 500
            for i in range(0, len(rows), CHUNK_SIZE):
                chunk = rows[i : i + CHUNK_SIZE]
                stmt = pg_insert(AssetPriceHistory).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_symbol_price_date",
                    set_={"price_eur": stmt.excluded.price_eur, "source": stmt.excluded.source},
                )
                await db.execute(stmt)
            await db.commit()
    except Exception as e:
        logger.warning("Failed to persist prices for %s to DB: %s", symbol, e)


async def _load_prices_from_db(symbol: str, days: int):
    """Load price history from PostgreSQL. Returns (dates, prices) or ([], [])."""
    try:
        cutoff = datetime.utcnow().date() - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AssetPriceHistory.price_date, AssetPriceHistory.price_eur)
                .where(
                    AssetPriceHistory.symbol == symbol.upper(),
                    AssetPriceHistory.price_date >= cutoff,
                )
                .order_by(AssetPriceHistory.price_date)
            )
            rows = result.all()
            if not rows:
                return [], []
            dates = [datetime.combine(row[0], datetime.min.time()) for row in rows]
            prices = [float(row[1]) for row in rows]
            return dates, prices
    except Exception as e:
        logger.warning("Failed to load prices from DB for %s: %s", symbol, e)
        return [], []


async def _fetch_and_cache_all():
    """Fetch history for all assets and store in Redis + PostgreSQL."""
    redis = _get_redis()
    assets = await _get_all_crypto_symbols()

    if not assets:
        logger.info("No assets to cache history for")
        return 0

    coingecko_key = getattr(settings, "COINGECKO_API_KEY", None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)
    cached_count = 0
    days = DEFAULT_CACHE_DAYS

    try:
        for symbol, asset_type in assets:
            key = _cache_key(symbol, days)

            # Skip if already cached and not expired
            existing = redis.get(key)
            if existing:
                try:
                    data = json.loads(existing)
                    # Check if data is recent enough (< 50 min old)
                    if data.get("fetched_at", 0) > datetime.utcnow().timestamp() - 3000:
                        logger.debug("Skipping %s — still fresh in cache", symbol)
                        cached_count += 1
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass

            try:
                dates, prices = await fetcher.get_history(symbol, asset_type, days=days)
                if dates and prices:
                    payload = json.dumps(
                        {
                            "dates": [d.isoformat() for d in dates],
                            "prices": prices,
                            "fetched_at": datetime.utcnow().timestamp(),
                        }
                    )
                    redis.setex(key, REDIS_HISTORY_TTL, payload)
                    redis.setex(f"{key}:fallback", REDIS_HISTORY_FALLBACK_TTL, payload)
                    # Persist to PostgreSQL for long-term storage
                    await _persist_prices_to_db(symbol, dates, prices)
                    cached_count += 1
                    logger.info("Cached %d data points for %s (%dd)", len(prices), symbol, days)
                else:
                    logger.warning("No history data for %s", symbol)
            except Exception as e:
                logger.warning("Failed to fetch history for %s: %s", symbol, e)

            # Rate limit: 7s between requests — CoinGecko free tier is shared
            # with price_updates task, so we need generous spacing
            await asyncio.sleep(7.0)

    finally:
        await fetcher.close()

    logger.info("History cache complete: %d/%d assets cached", cached_count, len(assets))
    return cached_count


@celery_app.task(name="app.tasks.history_cache.cache_historical_data")
def cache_historical_data():
    """Celery task: fetch and cache historical data for all assets."""
    logger.info("Starting historical data cache task...")
    result = _run_async(_fetch_and_cache_all())
    return {"cached": result}


async def _cache_single(symbol: str, asset_type: str, days: int = DEFAULT_CACHE_DAYS):
    """Fetch and cache history for a single asset."""
    redis = _get_redis()
    key = _cache_key(symbol, days)

    # Skip if already cached
    if redis.get(key):
        return True

    coingecko_key = getattr(settings, "COINGECKO_API_KEY", None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)
    try:
        dates, prices = await fetcher.get_history(symbol, asset_type, days=days)
        if dates and prices:
            payload = json.dumps(
                {
                    "dates": [d.isoformat() for d in dates],
                    "prices": prices,
                    "fetched_at": datetime.utcnow().timestamp(),
                }
            )
            redis.setex(key, REDIS_HISTORY_TTL, payload)
            redis.setex(f"{key}:fallback", REDIS_HISTORY_FALLBACK_TTL, payload)
            await _persist_prices_to_db(symbol, dates, prices)
            logger.info("Cached %d data points for %s (on-demand, %dd)", len(prices), symbol, days)
            return True
    except Exception as e:
        logger.warning("Failed to cache history for %s: %s", symbol, e)
    finally:
        await fetcher.close()
    return False


@celery_app.task(name="app.tasks.history_cache.cache_single_asset")
def cache_single_asset(symbol: str, asset_type: str):
    """Celery task: cache history for a single newly-added asset."""
    return _run_async(_cache_single(symbol, asset_type))


async def _find_missing_dates(symbol: str, start: datetime, end: datetime) -> list:
    """Find dates between start and end that have no price in asset_price_history.

    Returns a list of datetime objects for missing dates, limited to 50 per call
    to avoid overwhelming the per-date API.
    """
    from app.core.database import AsyncSessionLocal as _ASL

    try:
        async with _ASL() as db:
            from app.models.asset_price_history import AssetPriceHistory as _APH

            result = await db.execute(
                select(_APH.price_date).where(
                    _APH.symbol == symbol.upper(),
                    _APH.price_date >= start.date(),
                    _APH.price_date <= end.date(),
                )
            )
            existing_dates = {row[0] for row in result.all()}
    except Exception:
        return []

    missing = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while current.date() <= end.date():
        if current.date() not in existing_dates:
            missing.append(current)
        current += timedelta(days=1)

    # Limit to 50 oldest missing dates per run to respect rate limits
    return missing[:50]


async def _deep_backfill_all():
    """Deep backfill: fetch ALL historical prices since the earliest transaction.

    Uses /market_chart/range to go beyond the 365-day /market_chart limit.
    Persists everything to PostgreSQL so subsequent requests are instant.
    """
    from app.core.database import engine as _engine
    from app.models.transaction import Transaction

    redis = _get_redis()

    # Dispose engine connections to avoid 'attached to different loop' errors
    # when a previous Celery task used AsyncSessionLocal on a different event loop.
    await _engine.dispose()

    async with AsyncSessionLocal() as db:
        # 1. Get all unique symbols with their earliest transaction dates
        result = await db.execute(
            select(
                Asset.symbol,
                Asset.asset_type,
                func.min(func.coalesce(Transaction.executed_at, Transaction.created_at)).label("first_tx"),
            )
            .join(Transaction, Transaction.asset_id == Asset.id)
            .where(Asset.quantity > 0)
            .group_by(Asset.symbol, Asset.asset_type)
        )
        assets = [(row[0].upper(), row[1].value, row[2]) for row in result.all()]

        if not assets:
            logger.info("Deep backfill: no assets found")
            return 0

        # 2. Get existing coverage counts per symbol in one query
        coverage_result = await db.execute(
            select(
                AssetPriceHistory.symbol,
                func.count().label("cnt"),
            ).group_by(AssetPriceHistory.symbol)
        )
        coverage_map = {row[0]: row[1] for row in coverage_result.all()}

    coingecko_key = getattr(settings, "COINGECKO_API_KEY", None) or None
    fetcher = HistoricalDataFetcher(coingecko_api_key=coingecko_key)
    filled = 0

    try:
        for symbol, asset_type, first_tx in assets:
            if asset_type not in ("crypto",):
                continue

            if first_tx is None:
                continue

            # Normalize first_tx to naive
            if hasattr(first_tx, "tzinfo") and first_tx.tzinfo is not None:
                first_tx = first_tx.replace(tzinfo=None)

            existing_count = coverage_map.get(symbol, 0)
            today = datetime.utcnow()
            total_days_needed = (today - first_tx).days + 1

            # If we already have >80% of needed data, just fetch the last 365 days
            if existing_count > total_days_needed * 0.8:
                logger.info(
                    "Deep backfill: %s already has %d/%d points, refreshing recent",
                    symbol,
                    existing_count,
                    total_days_needed,
                )
                try:
                    dates, prices = await fetcher.get_history(symbol, asset_type, days=365)
                    if dates and prices:
                        await _persist_prices_to_db(symbol, dates, prices)
                        payload = json.dumps(
                            {
                                "dates": [d.isoformat() for d in dates],
                                "prices": prices,
                                "fetched_at": today.timestamp(),
                            }
                        )
                        key = _cache_key(symbol, DEFAULT_CACHE_DAYS)
                        redis.setex(key, REDIS_HISTORY_TTL, payload)
                        redis.setex(f"{key}:fallback", REDIS_HISTORY_FALLBACK_TTL, payload)
                        filled += 1
                except Exception as e:
                    logger.warning("Deep backfill: refresh failed for %s: %s", symbol, e)
                await asyncio.sleep(7.0)
                continue

            # Fetch in chunks via /market_chart/range (handles >365 days)
            logger.info(
                "Deep backfill: %s needs %d days of history (have %d), fetching...",
                symbol,
                total_days_needed,
                existing_count,
            )

            all_dates = []
            all_prices = []

            # Split into 365-day chunks, oldest first
            chunk_start = first_tx
            while chunk_start < today:
                chunk_end = min(chunk_start + timedelta(days=365), today)
                try:
                    dates, prices = await fetcher.get_crypto_history_range(symbol, chunk_start, chunk_end)
                    if dates and prices:
                        all_dates.extend(dates)
                        all_prices.extend(prices)
                        logger.info(
                            "Deep backfill: %s chunk %s→%s: %d points",
                            symbol,
                            chunk_start.date(),
                            chunk_end.date(),
                            len(dates),
                        )
                except Exception as e:
                    logger.warning(
                        "Deep backfill: chunk failed for %s (%s→%s): %s",
                        symbol,
                        chunk_start.date(),
                        chunk_end.date(),
                        e,
                    )

                chunk_start = chunk_end + timedelta(days=1)
                await asyncio.sleep(7.0)  # Rate limit between chunks

            # Always also fetch via standard /market_chart (365d, daily granularity)
            # because /range on free tier returns hourly data or 401 for old ranges
            try:
                std_dates, std_prices = await fetcher.get_history(symbol, asset_type, days=365)
                if std_dates and std_prices:
                    all_dates.extend(std_dates)
                    all_prices.extend(std_prices)
                    logger.info("Deep backfill: %s standard 365d fetch: %d points", symbol, len(std_dates))
                    await asyncio.sleep(7.0)
            except Exception as e:
                logger.warning("Deep backfill: standard fetch failed for %s: %s", symbol, e)

            # Persist all fetched data to PostgreSQL
            if all_dates and all_prices:
                await _persist_prices_to_db(symbol, all_dates, all_prices)

            # Yahoo Finance fallback for dates beyond CoinGecko's 365-day free limit
            # Dynamically resolves Yahoo tickers from symbol_map.py
            from app.core.symbol_map import get_yahoo_symbol

            yf_symbol = get_yahoo_symbol(symbol)
            if yf_symbol:
                try:
                    yf_dates, yf_prices = await fetcher.get_stock_history(yf_symbol, days=1825)
                    if yf_dates and yf_prices:
                        await _persist_prices_to_db(symbol, yf_dates, yf_prices, source="yahoo")
                        all_dates.extend(yf_dates)
                        all_prices.extend(yf_prices)
                        logger.info("Deep backfill: %s Yahoo fallback: %d points", symbol, len(yf_dates))
                except Exception as e:
                    logger.warning("Deep backfill: Yahoo fallback failed for %s: %s", symbol, e)

            # Fill remaining gaps using per-date /coins/{id}/history endpoint
            # This covers dates within CoinGecko's 365-day window that earlier fetches missed
            gap_dates = await _find_missing_dates(symbol, first_tx, today)
            if gap_dates:
                logger.info(
                    "Deep backfill: %s has %d missing dates, filling via per-date API...", symbol, len(gap_dates)
                )
                gap_filled = 0
                for gap_date in gap_dates:
                    try:
                        price = await fetcher.get_coin_price_by_date(symbol, gap_date)
                        if price is not None:
                            await _persist_prices_to_db(
                                symbol,
                                [gap_date],
                                [price],
                            )
                            all_dates.append(gap_date)
                            all_prices.append(price)
                            gap_filled += 1
                        await asyncio.sleep(15.0)  # 15s between per-date calls
                    except Exception as e:
                        logger.warning(
                            "Deep backfill: per-date fetch failed for %s on %s: %s", symbol, gap_date.date(), e
                        )
                        await asyncio.sleep(15.0)
                logger.info(
                    "Deep backfill: %s filled %d/%d gap dates via per-date API", symbol, gap_filled, len(gap_dates)
                )

            # Update Redis with the most recent 365 days
            if all_dates and all_prices:
                # Sort by date for correct Redis payload
                date_price_pairs = sorted(zip(all_dates, all_prices), key=lambda x: x[0])
                recent_pairs = date_price_pairs[-365:]
                payload = json.dumps(
                    {
                        "dates": [d.isoformat() for d, _ in recent_pairs],
                        "prices": [p for _, p in recent_pairs],
                        "fetched_at": today.timestamp(),
                    }
                )
                key = _cache_key(symbol, DEFAULT_CACHE_DAYS)
                redis.setex(key, REDIS_HISTORY_TTL, payload)
                redis.setex(f"{key}:fallback", REDIS_HISTORY_FALLBACK_TTL, payload)
                filled += 1
                logger.info("Deep backfill: %s complete — %d total points", symbol, len(all_dates))

    finally:
        await fetcher.close()

    logger.info("Deep backfill complete: %d/%d assets filled", filled, len(assets))
    return filled


@celery_app.task(name="app.tasks.history_cache.deep_backfill_prices")
def deep_backfill_prices():
    """Celery task: deep backfill ALL historical prices since first transaction."""
    logger.info("Starting deep historical price backfill...")
    result = _run_async(_deep_backfill_all())
    return {"filled": result}


def get_cached_history(symbol: str, days: int = 90):
    """Read cached history from Redis, falling back to PostgreSQL.

    Returns (dates, prices) or ([], []).
    Tries: exact Redis key → 365d Redis key → legacy 90d key → PostgreSQL.
    """
    redis = _get_redis()

    # Try exact key first
    key = _cache_key(symbol, days)
    raw = redis.get(key) or redis.get(f"{key}:fallback")

    # Fall back to the full 365d cache and trim
    if not raw and days != DEFAULT_CACHE_DAYS:
        full_key = _cache_key(symbol, DEFAULT_CACHE_DAYS)
        raw = redis.get(full_key) or redis.get(f"{full_key}:fallback")

    # Legacy: try old 90-day key for backwards compatibility
    if not raw and days != 90:
        legacy_key = _cache_key(symbol, 90)
        raw = redis.get(legacy_key) or redis.get(f"{legacy_key}:fallback")

    if raw:
        try:
            data = json.loads(raw)
            dates = [datetime.fromisoformat(d) for d in data["dates"]]
            prices = data["prices"]
            # Trim to requested days
            if len(dates) > days:
                return dates[-days:], prices[-days:]
            return dates, prices
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse cached history for %s: %s", symbol, e)

    # Final fallback: PostgreSQL persistent storage
    try:
        dates, prices = _run_async(_load_prices_from_db(symbol, days))
        if dates and prices:
            logger.info("Loaded %d prices for %s from DB (Redis miss)", len(prices), symbol)
            return dates, prices
    except Exception as e:
        logger.warning("DB fallback failed for %s: %s", symbol, e)

    return [], []
