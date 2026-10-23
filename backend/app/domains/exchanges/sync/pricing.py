import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.exchanges.sync.pairs import fiat_anchor
from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.service import FxService
from app.domains.market_data.prices.service import price_feed

logger = logging.getLogger(__name__)

FX_HISTORY_START = date(2017, 1, 1)
EUR = "EUR"


class TradeFx:
    """Devise et taux EUR du jour d'un ordre ; sans taux connu, l'ordre reste en EUR sans taux."""

    def __init__(self, service: FxService | None) -> None:
        self._service = service

    @classmethod
    async def seeded(cls, session: AsyncSession) -> "TradeFx":
        service = FxService(FxRateRepository(session))
        try:
            await service.refresh("USD", EUR, FX_HISTORY_START)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Historique USD/EUR indisponible (%s) : ordres en dollars gardés en EUR", exc)
            return cls(None)
        return cls(service)

    async def resolve(self, quote: str | None, executed_at: datetime) -> tuple[str, Decimal | None]:
        anchor = fiat_anchor(quote)
        if anchor is None or anchor == EUR or self._service is None:
            return EUR, None
        rate = await self._service.rate_on(executed_at.date(), anchor, EUR)
        if rate is None:
            logger.warning("Aucun taux %s/EUR au %s : ordre gardé en EUR", anchor, executed_at.date())
            return EUR, None
        return anchor, rate


async def market_price(symbol: str, fallback: Decimal | None) -> Decimal:
    """Cours EUR de la crypto ; à défaut son dernier cours connu, et zéro pour un jeton jamais coté."""
    quote = await price_feed.quote(symbol, "crypto")
    if quote is not None:
        return quote.price
    logger.warning("Cours de %s indisponible : dernier cours connu retenu (%s)", symbol, fallback or 0)
    return fallback or Decimal("0")
