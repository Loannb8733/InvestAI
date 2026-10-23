import logging
from datetime import date
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.frankfurter.dev/v1"
TIMEOUT_S = 15.0


async def fetch_daily_rates(base: str, quote: str, start: date, end: date) -> dict[date, Decimal]:
    """Taux de référence BCE quotidiens de ``base`` vers ``quote`` entre deux dates (incluses)."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        response = await client.get(
            f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}", params={"base": base, "symbols": quote}
        )
        response.raise_for_status()
        by_day: dict[str, dict[str, float]] = response.json().get("rates") or {}
    if not by_day:
        logger.warning("Frankfurter returned no rates for %s->%s %s..%s", base, quote, start, end)
    return {date.fromisoformat(day): Decimal(str(values[quote])) for day, values in by_day.items() if quote in values}
