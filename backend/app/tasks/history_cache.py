"""Task to pre-fetch and cache historical price data in Redis + PostgreSQL.

This avoids CoinGecko 429 errors on the Analytics page by fetching
historical data in the background with proper rate limiting.
PostgreSQL provides persistent storage; Redis is the fast-read layer.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import redis_async_url, redis_client_kwargs
from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset
from app.models.asset_price_history import AssetPriceHistory
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

REDIS_HISTORY_PREFIX = "hist:"
REDIS_HISTORY_TTL = 3600  # 1 hour
REDIS_HISTORY_FALLBACK_TTL = 86400  # 24 hours — stale-but-usable fallback
# Fetch 365 days by default so all timeframes (24h–1y) are served from one cache entry
DEFAULT_CACHE_DAYS = 365


# Client partagé par processus. Un client neuf à chaque lecture ouvrait une
# connexion par symbole — deux CLIENT SETINFO chacune, facturées par Upstash :
# 30 des 120 commandes d'un tableau de bord recalculé (mesuré le 2026-09-15).
# Le PID garde la réutilisation sûre après un fork (worker Celery prefork) :
# un processus enfant ne partage jamais la connexion de son parent.
_client: Optional[Redis] = None
_client_pid: Optional[int] = None


def _get_redis() -> Redis:
    global _client, _client_pid
    if _client is None or _client_pid != os.getpid():
        url = redis_async_url()  # same cleaned URL used by async clients
        _client = Redis.from_url(url, decode_responses=True, **redis_client_kwargs())
        _client_pid = os.getpid()
    return _client


def _cache_key(symbol: str, days: int) -> str:
    """Build a Redis key that includes the period."""
    return f"{REDIS_HISTORY_PREFIX}{symbol.upper()}_{days}"


def _lire_cache(redis: Redis, key: str) -> Optional[str]:
    """Lit une clé du cache ; une panne Redis vaut « pas en cache »."""
    try:
        return redis.get(key)
    except Exception as e:  # noqa: BLE001 — le cache ne doit jamais faire tomber l'appelant
        logger.warning("Cache Redis illisible pour %s (traité comme absent) : %s", key, e)
        return None


def _ecrire_cache(redis: Redis, key: str, payload: str) -> bool:
    """Écrit une entrée et sa copie de secours ; une panne Redis se voit, sans plus.

    À appeler *après* la persistance en base : `asset_price_history` est la
    copie durable, celle qui sert le tableau de bord quand Redis manque. Écrire
    Redis d'abord, dans le même bloc, faisait sauter la persistance sur une
    écriture refusée — journaux Render du 2026-09-15, quota Upstash épuisé :
    « Fetched 366 data points for TAO » puis « Failed to fetch history for TAO:
    max requests limit exceeded ». Les données étaient là, et perdues.
    """
    try:
        redis.setex(key, REDIS_HISTORY_TTL, payload)
        redis.setex(f"{key}:fallback", REDIS_HISTORY_FALLBACK_TTL, payload)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache Redis non écrit pour %s (données persistées en base) : %s", key, e)
        return False


async def _get_all_crypto_symbols() -> list:
    """Get all unique crypto symbols from DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Asset.symbol, Asset.asset_type).where(Asset.quantity > 0).distinct())
        return [(row[0].upper(), row[1].value) for row in result.all()]


async def _persist_prices_to_db(symbol: str, dates: list, prices: list, source: str = "coingecko"):
    """Upsert price data into asset_price_history AND mirror the latest
    price into assets.current_price for every (non-crowdfunding) row of
    that symbol.

    Deduplicates by (symbol, price_date) before inserting to avoid
    'ON CONFLICT DO UPDATE cannot affect row a second time' errors
    when CoinGecko returns duplicate dates at granularity boundaries.

    Mirroring assets.current_price keeps the column live for endpoints
    that historically used it directly (balance-gaps, crowdfunding KPIs,
    metrics service current-value snapshots).
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
                    set_={
                        "price_eur": stmt.excluded.price_eur,
                        "source": stmt.excluded.source,
                    },
                )
                await db.execute(stmt)

            # Mirror the latest price into assets.current_price (non-crowdfunding only).
            # Crowdfunding NFTs (TOKIMO) carry their own user-entered "invested" price
            # — never overwrite those.
            latest = max(rows, key=lambda r: r["price_date"])
            from sqlalchemy import text as _text

            await db.execute(
                _text(
                    "UPDATE assets SET current_price = :px,"
                    " last_price_update = :upd"
                    " WHERE symbol = :sym AND asset_type != 'CROWDFUNDING'"
                ),
                {
                    "px": latest["price_eur"],
                    "upd": datetime.now(timezone.utc),
                    "sym": symbol.upper(),
                },
            )
            await db.commit()
    except Exception as e:
        logger.warning("Failed to persist prices for %s to DB: %s", symbol, e)


def _charger_prix_depuis_db_sync(symbol: str, days: int):
    """Même lecture que `_load_prices_from_db`, sans boucle d'événements.

    `get_cached_history` est synchrone et appelée depuis des services web qui,
    eux, tournent dans une boucle. Y faire `run_async(...)` échouait : on ne peut
    pas démarrer une boucle à l'intérieur d'une boucle. L'exception était avalée
    par le `except` voisin, la coroutine jamais attendue, et **le repli
    PostgreSQL ne fonctionnait dans aucun chemin HTTP** — vérifié : 91 prix
    rendus depuis un script, 0 depuis un endpoint.

    Un moteur synchrone supprime la question : il n'y a plus de boucle à créer.
    """
    from sqlalchemy import create_engine, text

    moteur = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    try:
        limite = datetime.now(timezone.utc).date() - timedelta(days=days)
        with moteur.connect() as conn:
            lignes = conn.execute(
                text(
                    "SELECT price_date, price_eur FROM asset_price_history"
                    " WHERE symbol = :sym AND price_date >= :limite"
                    " ORDER BY price_date"
                ),
                {"sym": symbol.upper(), "limite": limite},
            ).fetchall()
        if not lignes:
            return [], []
        return (
            [datetime.combine(ligne[0], datetime.min.time()) for ligne in lignes],
            [float(ligne[1]) for ligne in lignes],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Repli PostgreSQL indisponible pour %s : %s", symbol, exc)
        return [], []
    finally:
        moteur.dispose()


async def _load_prices_from_db(symbol: str, days: int):
    """Load price history from PostgreSQL. Returns (dates, prices) or ([], [])."""
    try:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
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
            existing = _lire_cache(redis, key)
            if existing:
                try:
                    data = json.loads(existing)
                    # Check if data is recent enough (< 50 min old)
                    if data.get("fetched_at", 0) > datetime.now(timezone.utc).timestamp() - 3000:
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
                            "fetched_at": datetime.now(timezone.utc).timestamp(),
                        }
                    )
                    # Persist to PostgreSQL first (durable), then cache best-effort
                    await _persist_prices_to_db(symbol, dates, prices)
                    _ecrire_cache(redis, key, payload)
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
    result = run_async(_fetch_and_cache_all())
    return {"cached": result}


async def _cache_single(symbol: str, asset_type: str, days: int = DEFAULT_CACHE_DAYS):
    """Fetch and cache history for a single asset."""
    redis = _get_redis()
    key = _cache_key(symbol, days)

    # Skip if already cached
    if _lire_cache(redis, key):
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
                    "fetched_at": datetime.now(timezone.utc).timestamp(),
                }
            )
            await _persist_prices_to_db(symbol, dates, prices)
            _ecrire_cache(redis, key, payload)
            logger.info(
                "Cached %d data points for %s (on-demand, %dd)",
                len(prices),
                symbol,
                days,
            )
            return True
    except Exception as e:
        logger.warning("Failed to cache history for %s: %s", symbol, e)
    finally:
        await fetcher.close()
    return False


@celery_app.task(name="app.tasks.history_cache.cache_single_asset")
def cache_single_asset(symbol: str, asset_type: str):
    """Celery task: cache history for a single newly-added asset."""
    return run_async(_cache_single(symbol, asset_type))


# Pré-chargements confiés à la boucle du processus web (sans worker) : la tâche
# en cours par symbole, pour ne pas la lancer deux fois, et l'instant du dernier
# essai, pour ne pas réinterroger CoinGecko à chaque recalcul pour un symbole
# qui n'a pas d'historique.
_prechargements_en_cours: Dict[str, "asyncio.Task"] = {}
_dernier_essai: Dict[str, float] = {}
_DELAI_ENTRE_ESSAIS = 3600.0


def planifier_cache_historique(symbol: str, asset_type: str) -> str:
    """Programme le pré-chargement d'historique d'un actif, selon l'infrastructure.

    Avec un worker Celery (docker-compose) : mise en file, comme avant. Sans
    worker (Render, offre gratuite), `.delay()` empilait la tâche dans Redis —
    8 commandes Upstash (4 LLEN, MULTI, SADD, LPUSH, EXEC) mesurées par appel —
    sans que personne ne la consomme jamais : la file `celery` grossissait à
    chaque tableau de bord recalculé avec un symbole sans historique. Le travail
    est alors confié à la boucle asyncio du processus web, quand il y en a une.

    Renvoie où le travail est parti : « file », « boucle », « deja » (même
    symbole en cours ou essayé il y a moins d'une heure) ou « ignore » (pas de
    boucle en cours).
    """
    if settings.CELERY_WORKER_AVAILABLE:
        cache_single_asset.delay(symbol, asset_type)
        return "file"

    cle = symbol.upper()
    maintenant = time.monotonic()
    if (
        cle in _prechargements_en_cours
        or maintenant - _dernier_essai.get(cle, -_DELAI_ENTRE_ESSAIS) < _DELAI_ENTRE_ESSAIS
    ):
        return "deja"
    try:
        boucle = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Pré-chargement de %s non planifié : ni worker Celery ni boucle en cours", cle)
        return "ignore"

    _dernier_essai[cle] = maintenant
    tache = boucle.create_task(_cache_single(symbol, asset_type))
    _prechargements_en_cours[cle] = tache
    tache.add_done_callback(lambda _t, _cle=cle: _prechargements_en_cours.pop(_cle, None))
    return "boucle"


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
            today = datetime.now(timezone.utc)
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
                    logger.info(
                        "Deep backfill: %s standard 365d fetch: %d points",
                        symbol,
                        len(std_dates),
                    )
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
                        logger.info(
                            "Deep backfill: %s Yahoo fallback: %d points",
                            symbol,
                            len(yf_dates),
                        )
                except Exception as e:
                    logger.warning("Deep backfill: Yahoo fallback failed for %s: %s", symbol, e)

            # Fill remaining gaps using per-date /coins/{id}/history endpoint
            # This covers dates within CoinGecko's 365-day window that earlier fetches missed
            gap_dates = await _find_missing_dates(symbol, first_tx, today)
            if gap_dates:
                logger.info(
                    "Deep backfill: %s has %d missing dates, filling via per-date API...",
                    symbol,
                    len(gap_dates),
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
                            "Deep backfill: per-date fetch failed for %s on %s: %s",
                            symbol,
                            gap_date.date(),
                            e,
                        )
                        await asyncio.sleep(15.0)
                logger.info(
                    "Deep backfill: %s filled %d/%d gap dates via per-date API",
                    symbol,
                    gap_filled,
                    len(gap_dates),
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
                logger.info(
                    "Deep backfill: %s complete — %d total points",
                    symbol,
                    len(all_dates),
                )

    finally:
        await fetcher.close()

    logger.info("Deep backfill complete: %d/%d assets filled", filled, len(assets))
    return filled


@celery_app.task(name="app.tasks.history_cache.deep_backfill_prices")
def deep_backfill_prices():
    """Celery task: deep backfill ALL historical prices since first transaction."""
    logger.info("Starting deep historical price backfill...")
    result = run_async(_deep_backfill_all())
    return {"filled": result}


def _cles_candidates(symbol: str, days: int) -> List[str]:
    """Clés à essayer pour un symbole, par ordre de préférence.

    Clé exacte → 365 jours (tronquée ensuite) → ancienne clé 90 jours, chacune
    suivie de sa copie de secours à 24 h.
    """
    cles = []
    periodes = [days]
    if days != DEFAULT_CACHE_DAYS:
        periodes.append(DEFAULT_CACHE_DAYS)
    if days != 90:
        periodes.append(90)
    for periode in periodes:
        cle = _cache_key(symbol, periode)
        cles += [cle, f"{cle}:fallback"]
    return cles


def get_cached_histories(symbols: List[str], days: int = 90) -> Dict[str, Tuple[list, list]]:
    """Lit l'historique de plusieurs symboles en **une seule** commande Redis.

    Renvoie ``{symbole: (dates, prices)}`` pour chaque symbole demandé, avec
    ``([], [])`` quand rien n'est disponible. Même ordre de préférence et même
    repli PostgreSQL que la lecture unitaire.

    Upstash facture chaque commande. Lire symbole par symbole coûtait jusqu'à
    six GET chacun (clé exacte, 365 jours, 90 jours, et leurs secours) : environ
    40 des 120 commandes d'un tableau de bord recalculé. Un MGET compte pour un.
    """
    demandes = list(dict.fromkeys(symbols))
    candidates = {symbole: _cles_candidates(symbole, days) for symbole in demandes}
    toutes = [cle for cles in candidates.values() for cle in cles]
    valeurs: Dict[str, Optional[str]] = {}

    # Toute la lecture Redis sous une même garde. Sans elle, une base
    # injoignable levait ici — et le repli PostgreSQL annoncé par la docstring
    # n'était jamais atteint. L'exception remontait jusqu'à
    # `build_portfolio_value_series`, puis à `_get_dashboard_impl`, et l'écran
    # d'accueil entier répondait 500 : constaté en production le 2026-09-10,
    # les jours où Upstash mettait la base en veille.
    #
    # Un cache dont l'indisponibilité fait tomber la page qu'il devait
    # accélérer est pire que pas de cache du tout.
    if toutes:
        try:
            valeurs = dict(zip(toutes, _get_redis().mget(toutes)))
        except Exception as e:  # noqa: BLE001 — le cache ne doit jamais faire tomber l'appelant
            for symbole in demandes:
                logger.warning("Cache Redis injoignable pour %s (repli sur PostgreSQL) : %s", symbole, e)

    resultats: Dict[str, Tuple[list, list]] = {}
    for symbole in demandes:
        raw = next((valeurs[cle] for cle in candidates[symbole] if valeurs.get(cle)), None)
        if raw:
            try:
                data = json.loads(raw)
                dates = [datetime.fromisoformat(d) for d in data["dates"]]
                prices = data["prices"]
                # Trim to requested days
                if len(dates) > days:
                    resultats[symbole] = (dates[-days:], prices[-days:])
                else:
                    resultats[symbole] = (dates, prices)
                continue
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse cached history for %s: %s", symbole, e)

        # Final fallback: PostgreSQL persistent storage
        resultats[symbole] = ([], [])
        try:
            dates, prices = _charger_prix_depuis_db_sync(symbole, days)
            if dates and prices:
                logger.info("Loaded %d prices for %s from DB (Redis miss)", len(prices), symbole)
                resultats[symbole] = (dates, prices)
        except Exception as e:
            logger.warning("DB fallback failed for %s: %s", symbole, e)

    return resultats


def get_cached_history(symbol: str, days: int = 90):
    """Read cached history from Redis, falling back to PostgreSQL.

    Returns (dates, prices) or ([], []).
    Tries: exact Redis key → 365d Redis key → legacy 90d key → PostgreSQL.
    Pour plusieurs symboles, préférer :func:`get_cached_histories` (une commande).
    """
    return get_cached_histories([symbol], days)[symbol]
