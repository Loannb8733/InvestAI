from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domains.market_data.fx.cold_start import cold_start_rate
from app.domains.market_data.fx.frankfurter import fetch_daily_rates
from app.domains.market_data.fx.reference import resolve_rate
from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.spot import SpotRates, spot_rates


@dataclass(frozen=True)
class FxQuote:
    rate: Decimal
    stale: bool


class FxService:
    """Taux de change : au comptant, de référence BCE à une date, et rafraîchissement du référentiel."""

    def __init__(self, repository: FxRateRepository, spot: SpotRates = spot_rates) -> None:
        self._repository = repository
        self._spot = spot
        self._series: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}

    async def latest(self, from_ccy: str, to_ccy: str) -> FxQuote | None:
        """Taux actuel : au comptant si disponible, sinon dernier taux BCE puis taux de démarrage, signalés périmés."""
        live = await self._spot.get(from_ccy, to_ccy)
        if live is not None:
            return FxQuote(live, stale=False)
        known = await self.rate_on(datetime.now(UTC).date(), from_ccy, to_ccy, allow_inverse=True)
        if known is not None:
            return FxQuote(known, stale=True)
        fallback = cold_start_rate(from_ccy, to_ccy)
        return FxQuote(fallback, stale=True) if fallback is not None else None

    async def rate_on(self, day: date, from_ccy: str, to_ccy: str, *, allow_inverse: bool = False) -> Decimal | None:
        """Taux BCE en vigueur à ``day``, sans réseau ; None si l'historique ne le couvre pas."""
        base, quote = from_ccy.upper(), to_ccy.upper()
        if base == quote:
            return Decimal("1")
        direct = resolve_rate(day, await self._load(base, quote))
        if direct is not None or not allow_inverse:
            return direct
        inverse = resolve_rate(day, await self._load(quote, base))
        return Decimal("1") / inverse if inverse else None

    async def refresh(self, from_ccy: str, to_ccy: str, earliest: date) -> int:
        """Complète le référentiel BCE jusqu'à aujourd'hui (tout l'historique la première fois)."""
        base, quote = from_ccy.upper(), to_ccy.upper()
        today = datetime.now(UTC).date()
        last = await self._repository.last_date(base, quote)
        if last is not None and last >= today:
            return 0
        rates = await fetch_daily_rates(base, quote, last or earliest, today)
        inserted = await self._repository.insert_missing(base, quote, rates)
        self._series.pop((base, quote), None)
        return inserted

    async def _load(self, base: str, quote: str) -> list[tuple[date, Decimal]]:
        if (base, quote) not in self._series:
            self._series[(base, quote)] = await self._repository.series(base, quote)
        return self._series[(base, quote)]
