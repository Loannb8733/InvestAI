"""Indice Fear & Greed d'alternative.me."""

import logging

import httpx

logger = logging.getLogger(__name__)

_FNG_URL = "https://api.alternative.me/fng/?limit=1"
_HTTP_OK = 200


async def fetch_fear_greed_index(*, timeout: float = 5.0) -> int | None:
    """Indice courant de 0 à 100 ; None en cas d'échec, chaque appelant garde son repli."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(_FNG_URL)
            if response.status_code == _HTTP_OK:
                data = response.json()
                if data.get("data"):
                    return int(data["data"][0].get("value", 50))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to fetch Fear & Greed Index: %s", exc)
    return None
