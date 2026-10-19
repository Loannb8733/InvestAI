import asyncio
import logging
import time
from datetime import UTC, datetime

from app.core.config import settings
from app.core.db.session import session_factory
from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.service import FxService
from app.domains.market_data.history.benchmarks import MARKET_REFERENCES
from app.domains.market_data.history.coingecko import CoinGeckoHistory
from app.domains.market_data.history.repository import HistoryRepository
from app.domains.market_data.history.service import HistoryService
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

SPACING_S = 7.0
RETRY_AFTER_S = 3600.0
QUOTED = frozenset({"crypto", "stock", "etf"})
NEARLY_COMPLETE = 0.8

_running: dict[str, asyncio.Task[bool]] = {}
_last_attempt: dict[str, float] = {}


async def refresh_symbol(symbol: str, asset_type: str) -> bool:
    """Rafraîchit un symbole et valide ; False si aucune source n'a répondu."""
    coingecko = CoinGeckoHistory()
    try:
        async with session_factory() as session:
            service = HistoryService(HistoryRepository(session), FxService(FxRateRepository(session)), coingecko)
            refreshed = await service.refresh(symbol, asset_type)
            await session.commit()
            return refreshed
    finally:
        await coingecko.close()


async def refresh_all() -> int:
    """Rafraîchit les actifs détenus et les références de marché sans cours du jour en base ; rend le nombre à jour."""
    async with session_factory() as session:
        repository = HistoryRepository(session)
        wanted = dict(await repository.quoted_holdings())
        last_days = await repository.last_days()
    wanted.update(MARKET_REFERENCES)
    today = datetime.now(UTC).date()
    up_to_date = 0
    for symbol, kind in wanted.items():
        if last_days.get(symbol) == today:
            up_to_date += 1
            continue
        if await refresh_symbol(symbol, kind):
            up_to_date += 1
        await asyncio.sleep(SPACING_S)
    logger.info("Historique à jour pour %d/%d symboles", up_to_date, len(wanted))
    return up_to_date


async def backfill_all() -> int:
    """Remonte l'historique des cryptos détenues jusqu'à leur première transaction ; rend le nombre traité."""
    async with session_factory() as session:
        repository = HistoryRepository(session)
        firsts = await repository.first_crypto_trades()
        counts = await repository.counts()
    coingecko = CoinGeckoHistory()
    done = 0
    try:
        for symbol, first in firsts:
            needed = (datetime.now(UTC).replace(tzinfo=None) - first.replace(tzinfo=None)).days + 1
            async with session_factory() as session:
                service = HistoryService(HistoryRepository(session), FxService(FxRateRepository(session)), coingecko)
                if counts.get(symbol, 0) > needed * NEARLY_COMPLETE:
                    await service.refresh(symbol, "crypto")
                else:
                    await service.backfill(symbol, first)
                await session.commit()
            done += 1
            await asyncio.sleep(SPACING_S)
    finally:
        await coingecko.close()
    return done


def schedule_refresh(symbol: str, asset_type: str) -> str:
    """Programme le rafraîchissement d'un symbole hors de la requête en cours.

    Avec un worker Celery : mise en file. Sans worker : tâche sur la boucle du
    processus web, une seule par symbole et par heure. Rend « file », « boucle »,
    « deja » ou « ignore » (type sans cotation, ou aucune boucle en cours).
    """
    if asset_type not in QUOTED:
        return "ignore"
    if settings.CELERY_WORKER_AVAILABLE:
        refresh_one.delay(symbol, asset_type)
        return "file"
    key = symbol.upper()
    now = time.monotonic()
    if key in _running or now - _last_attempt.get(key, -RETRY_AFTER_S) < RETRY_AFTER_S:
        return "deja"
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Rafraîchissement de %s non planifié : ni worker Celery ni boucle en cours", key)
        return "ignore"
    _last_attempt[key] = now
    task = loop.create_task(refresh_symbol(key, asset_type))
    _running[key] = task

    def forget(_: asyncio.Task[bool]) -> None:
        _running.pop(key, None)

    task.add_done_callback(forget)
    return "boucle"


@celery_app.task(name="app.domains.market_data.history.tasks.refresh_history")  # type: ignore[untyped-decorator]
def refresh_history() -> dict[str, int]:
    return {"up_to_date": run_async(refresh_all())}


@celery_app.task(name="app.domains.market_data.history.tasks.refresh_one")  # type: ignore[untyped-decorator]
def refresh_one(symbol: str, asset_type: str) -> bool:
    return run_async(refresh_symbol(symbol, asset_type))


@celery_app.task(name="app.domains.market_data.history.tasks.backfill_history")  # type: ignore[untyped-decorator]
def backfill_history() -> dict[str, int]:
    return {"filled": run_async(backfill_all())}
