"""Shared market-sentiment data fetchers.

Single source of truth for the alternative.me Fear & Greed Index. Previously the
fetch/parse/error-handling block was copy-pasted across the prediction, regime
and insights services (6 call sites); this centralises the API contract so a
timeout/URL/parsing change only has to be made once.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_FNG_URL = "https://api.alternative.me/fng/?limit=1"


async def fetch_fear_greed_index(*, timeout: float = 5.0) -> Optional[int]:
    """Return the current Fear & Greed Index (0-100), or ``None`` on any failure.

    Behaviour-preserving replacement for the inline fetch blocks: all errors are
    swallowed and ``None`` is returned so each caller keeps its own
    fallback/default logic (e.g. defaulting to 50 or estimating from portfolio
    data).
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_FNG_URL)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    return int(data["data"][0].get("value", 50))
    except Exception as exc:  # noqa: BLE001 - sentiment is best-effort
        logger.debug("Failed to fetch Fear & Greed Index: %s", exc)
    return None
