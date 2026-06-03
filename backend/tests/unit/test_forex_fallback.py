"""Unit tests for robust forex fallback (FIN-04).

Pins the guarantee that the USD/EUR rate never silently collapses to the hardcoded
0.92 constant once a real rate has been observed: on a transient API outage we must
reuse the last-known rate, and the constant is only ever used on a true cold start.
The 0.92 path additionally emits a warning so the degradation is observable.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.price_service import PriceService


@pytest.fixture(autouse=True)
def _reset_class_cache():
    """The last-known rate lives on the class; isolate each test."""
    PriceService._eur_usd_rate = None
    PriceService._eur_usd_rate_ts = 0.0
    yield
    PriceService._eur_usd_rate = None
    PriceService._eur_usd_rate_ts = 0.0


@pytest.mark.asyncio
async def test_live_rate_is_used_and_cached():
    ps = PriceService()
    with patch.object(ps, "get_forex_rate", AsyncMock(return_value=Decimal("0.93"))):
        rate = await ps._get_eur_usd_rate()
    assert rate == Decimal("0.93")
    assert PriceService._eur_usd_rate == Decimal("0.93")


@pytest.mark.asyncio
async def test_outage_reuses_last_known_not_constant():
    ps = PriceService()
    # First call succeeds and seeds the last-known rate.
    with patch.object(ps, "get_forex_rate", AsyncMock(return_value=Decimal("0.95"))):
        await ps._get_eur_usd_rate()
    # Force cache expiry, then simulate an API outage.
    PriceService._eur_usd_rate_ts = 0.0
    with patch.object(ps, "get_forex_rate", AsyncMock(return_value=None)):
        rate = await ps._get_eur_usd_rate()
    # Must reuse the real last-known rate, NOT the 0.92 constant.
    assert rate == Decimal("0.95")


@pytest.mark.asyncio
async def test_cold_start_falls_back_to_constant_with_warning():
    ps = PriceService()
    with patch.object(ps, "get_forex_rate", AsyncMock(return_value=None)):
        with patch("app.services.price_service.logger") as mock_logger:
            rate = await ps._get_eur_usd_rate()
    assert rate == Decimal("0.92")
    assert mock_logger.warning.called
