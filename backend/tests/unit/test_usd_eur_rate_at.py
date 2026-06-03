"""Unit tests for historical USD→EUR resolution in the API-key trade import (FIN-01).

Before this fix, ``api_keys.py`` converted every USD-denominated trade with a single
*current* USD→EUR rate, baking years of FX drift into the stored EUR price of old trades.
``_usd_eur_rate_at`` resolves the rate *as of each trade's execution date* instead, with a
current-spot fallback so a missing/unreachable history never blocks an import. No DB/HTTP:
the FX service is faked.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.endpoints.api_keys import _usd_eur_rate_at


class _FakeFx:
    """Stand-in for FxHistoryService.get_rate returning a preset map (or raising)."""

    def __init__(self, rates=None, *, raises=False):
        self._rates = rates or {}
        self._raises = raises
        self.calls: list[tuple] = []

    async def get_rate(self, rate_date, from_ccy, to_ccy):
        self.calls.append((rate_date, from_ccy, to_ccy))
        if self._raises:
            raise RuntimeError("transient FX read error")
        return self._rates.get((from_ccy, to_ccy))


_D = date(2021, 5, 17)
_FALLBACK = 0.92


class TestUsdEurRateAt:
    @pytest.mark.asyncio
    async def test_uses_historical_rate_at_trade_date(self):
        # An old trade must NOT use the current rate: the 2021 rate is returned and the
        # lookup is anchored on the trade's own date.
        fx = _FakeFx({("USD", "EUR"): Decimal("0.8231")})
        rate = await _usd_eur_rate_at(fx, _D, _FALLBACK)
        assert rate == pytest.approx(0.8231)
        assert fx.calls == [(_D, "USD", "EUR")]

    @pytest.mark.asyncio
    async def test_no_fx_service_uses_fallback(self):
        rate = await _usd_eur_rate_at(None, _D, _FALLBACK)
        assert rate == _FALLBACK

    @pytest.mark.asyncio
    async def test_missing_history_uses_fallback(self):
        # Rate unavailable for that date -> fall back to current spot, never None/0.
        fx = _FakeFx({("USD", "EUR"): None})
        rate = await _usd_eur_rate_at(fx, _D, _FALLBACK)
        assert rate == _FALLBACK
        assert fx.calls == [(_D, "USD", "EUR")]

    @pytest.mark.asyncio
    async def test_fx_read_error_is_swallowed_to_fallback(self):
        # A transient read error must never break the import.
        fx = _FakeFx(raises=True)
        rate = await _usd_eur_rate_at(fx, _D, _FALLBACK)
        assert rate == _FALLBACK

    @pytest.mark.asyncio
    async def test_returns_float_not_decimal(self):
        # Caller multiplies a float price; the helper must hand back a plain float.
        fx = _FakeFx({("USD", "EUR"): Decimal("0.9120")})
        rate = await _usd_eur_rate_at(fx, _D, _FALLBACK)
        assert isinstance(rate, float)
        assert rate == pytest.approx(0.9120)
