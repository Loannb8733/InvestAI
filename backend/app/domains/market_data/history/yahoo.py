import logging
from datetime import UTC, datetime

import httpx

from app.domains.market_data.history.series import PriceSeries
from app.domains.market_data.prices.yahoo import CHART_URL, SUBUNITS

logger = logging.getLogger(__name__)

TIMEOUT_S = 30.0
RANGES = ((7, "5d"), (30, "1mo"), (90, "3mo"), (180, "6mo"), (365, "1y"), (730, "2y"))


def _range(days: int) -> str:
    return next((label for limit, label in RANGES if days <= limit), "5y")


async def yahoo_daily(ticker: str, days: int) -> tuple[PriceSeries, str] | None:
    """Clôtures quotidiennes et volumes dans la devise de cotation, avec cette devise ; None si Yahoo ne répond pas."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = await client.get(
                CHART_URL.format(ticker=ticker), params={"interval": "1d", "range": _range(days)}
            )
            response.raise_for_status()
            chart = response.json()["chart"]["result"][0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Historique Yahoo indisponible pour %s : %s", ticker, exc)
        return None
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    raw_volumes = quote.get("volume") or []
    raw_currency = str(chart.get("meta", {}).get("currency") or "USD")
    currency, divisor = SUBUNITS.get(raw_currency, (raw_currency.upper(), 1))
    rows = [
        (stamp, float(close) / float(divisor), raw_volumes[i] if i < len(raw_volumes) else None)
        for i, (stamp, close) in enumerate(zip(chart.get("timestamp") or [], closes, strict=False))
        if close is not None
    ]
    series = PriceSeries(
        dates=[datetime.fromtimestamp(stamp, tz=UTC).replace(tzinfo=None) for stamp, _, _ in rows],
        prices=[price for _, price, _ in rows],
        volumes=[float(volume or 0) for _, _, volume in rows] or None,
    )
    return series, currency
