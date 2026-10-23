import logging
import time
from decimal import Decimal

import httpx

from app.core.redis_client import _get_redis_txt

logger = logging.getLogger(__name__)

FIAT_CURRENCIES = frozenset({"EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN", "CZK"})
SPOT_URL = "https://api.exchangerate-api.com/v4/latest/{base}"
MEMO_TTL_S = 300
REDIS_TTL_S = 3600
HTTP_TIMEOUT_S = 10.0


def _redis_key(from_ccy: str, to_ccy: str) -> str:
    return f"forex:spot:{from_ccy}:{to_ccy}"


class SpotRates:
    """Taux de change au comptant : mémo du processus, puis Redis, puis exchangerate-api."""

    def __init__(self) -> None:
        self._memo: dict[tuple[str, str], tuple[float, Decimal]] = {}

    def clear(self) -> None:
        self._memo.clear()

    async def get(self, from_ccy: str, to_ccy: str) -> Decimal | None:
        """Unités de ``to_ccy`` pour 1 ``from_ccy`` ; None si un code n'est pas une monnaie ou si rien ne répond."""
        pair = (from_ccy.upper(), to_ccy.upper())
        if pair[0] not in FIAT_CURRENCIES or pair[1] not in FIAT_CURRENCIES:
            return None
        if pair[0] == pair[1]:
            return Decimal("1")
        memo = self._memo.get(pair)
        if memo and time.monotonic() - memo[0] < MEMO_TTL_S:
            return memo[1]
        rate = await self._from_redis(*pair) or await self._from_api(*pair)
        if rate is not None:
            self._memo[pair] = (time.monotonic(), rate)
        return rate

    async def _from_redis(self, from_ccy: str, to_ccy: str) -> Decimal | None:
        try:
            cached = await (await _get_redis_txt()).get(_redis_key(from_ccy, to_ccy))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis cache read error for forex: %s", exc)
            return None
        return Decimal(str(cached)) if cached else None

    async def _from_api(self, from_ccy: str, to_ccy: str) -> Decimal | None:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
                response = await client.get(SPOT_URL.format(base=from_ccy))
                response.raise_for_status()
                value = response.json().get("rates", {}).get(to_ccy)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching forex rate %s/%s: %s", from_ccy, to_ccy, exc)
            return None
        if not value:
            return None
        try:
            await (await _get_redis_txt()).setex(_redis_key(from_ccy, to_ccy), REDIS_TTL_S, str(value))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis cache write error for forex: %s", exc)
        return Decimal(str(value))


spot_rates = SpotRates()
