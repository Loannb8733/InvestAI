import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.symbol_map import get_yahoo_symbol
from app.domains.market_data.fx.service import FxService
from app.domains.market_data.history.coingecko import CoinGeckoHistory
from app.domains.market_data.history.repository import HistoryRepository
from app.domains.market_data.history.series import PriceSeries
from app.domains.market_data.history.yahoo import yahoo_daily
from app.domains.market_data.prices.service import price_feed

logger = logging.getLogger(__name__)

HISTORY_DAYS = 365
GAP_LIMIT = 50
GAP_SPACING_S = 15.0
CHUNK_SPACING_S = 7.0


class HistoryService:
    """Rafraîchissement réseau de l'historique quotidien en EUR, réservé aux tâches de fond."""

    def __init__(self, repository: HistoryRepository, fx: FxService, coingecko: CoinGeckoHistory) -> None:
        self._repository = repository
        self._fx = fx
        self._coingecko = coingecko

    async def refresh(self, symbol: str, asset_type: str) -> bool:
        """Récupère l'année écoulée, l'enregistre et recopie le dernier cours dans les actifs."""
        series, source = await self._fetch(symbol.upper(), asset_type, HISTORY_DAYS)
        if not series.prices:
            logger.warning("Aucun historique obtenu pour %s", symbol)
            return False
        await self._repository.upsert(symbol.upper(), series, source)
        await self._repository.mirror_current_price(symbol.upper(), series.prices[-1])
        return True

    async def backfill(self, symbol: str, first: datetime) -> int:
        """Complète l'historique d'une crypto depuis ``first`` : tranches annuelles, Yahoo, puis jours manquants."""
        symbol = symbol.upper()
        first = first.replace(tzinfo=None)
        today = datetime.now(UTC).replace(tzinfo=None)
        stored = 0
        start = first
        while start < today:
            end = min(start + timedelta(days=HISTORY_DAYS), today)
            chunk = await self._coingecko.between(symbol, start, end)
            if chunk.prices:
                stored += await self._repository.upsert(symbol, chunk, "coingecko")
            start = end + timedelta(days=1)
            await asyncio.sleep(CHUNK_SPACING_S)
        ticker = get_yahoo_symbol(symbol)
        listed = await yahoo_daily(ticker, 5 * HISTORY_DAYS) if ticker else None
        if listed is not None:
            stored += await self._repository.upsert(symbol, await self._in_eur(*listed), "yahoo")
        known = await self._repository.known_days(symbol, first.date(), today.date())
        missing = [first.date() + timedelta(days=n) for n in range((today - first).days + 1)]
        for day in [d for d in missing if d not in known][:GAP_LIMIT]:
            price = await price_feed.crypto_on(symbol, day)
            if price is not None:
                moment = datetime.combine(day, datetime.min.time())
                stored += await self._repository.upsert(symbol, PriceSeries([moment], [float(price)]), "coingecko")
            await asyncio.sleep(GAP_SPACING_S)
        return stored

    async def _fetch(self, symbol: str, asset_type: str, days: int) -> tuple[PriceSeries, str]:
        ticker: str | None = symbol
        if asset_type == "crypto":
            series = await self._coingecko.daily(symbol, days)
            if series.prices:
                return series, "coingecko"
            ticker = get_yahoo_symbol(symbol)
        listed = await yahoo_daily(ticker, days) if ticker else None
        if listed is None:
            return PriceSeries(), "yahoo"
        return await self._in_eur(*listed), "yahoo"

    async def _in_eur(self, series: PriceSeries, currency: str) -> PriceSeries:
        kept: list[int] = []
        rates: list[float] = []
        for index, moment in enumerate(series.dates):
            rate = await self._fx.rate_on(moment.date(), currency, "EUR", allow_inverse=True)
            if rate is not None:
                kept.append(index)
                rates.append(float(rate))
        if len(kept) < len(series.dates):
            logger.warning("%d cours en %s écartés faute de taux EUR", len(series.dates) - len(kept), currency)
        volumes = [series.volumes[i] for i in kept] if series.volumes is not None else None
        return PriceSeries(
            dates=[series.dates[i] for i in kept],
            prices=[series.prices[i] * rate for i, rate in zip(kept, rates, strict=True)],
            volumes=volumes,
        )
