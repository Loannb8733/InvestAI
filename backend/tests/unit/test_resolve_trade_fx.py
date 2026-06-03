"""Unit tests for trade FX resolution in the exchange sync (FIN-01).

Pins the guarantee that ``_resolve_trade_fx`` never labels a row with a foreign currency
unless a valid historical EUR rate exists. The fallback is always ("EUR", None), which is
"never worse than" the legacy hardcoded behaviour. No DB/HTTP: the FX service is faked.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.tasks.sync_exchanges import _resolve_trade_fx


class _FakeFx:
    """Stand-in for FxHistoryService.get_rate returning a preset map."""

    def __init__(self, rates: dict[tuple[str, str], Decimal | None]):
        self._rates = rates
        self.calls: list[tuple] = []

    async def get_rate(self, rate_date, from_ccy, to_ccy):
        self.calls.append((rate_date, from_ccy, to_ccy))
        return self._rates.get((from_ccy, to_ccy))


_TS = datetime(2024, 1, 17, 12, 0, tzinfo=timezone.utc)


class TestResolveTradeFx:
    @pytest.mark.asyncio
    async def test_usdt_quote_maps_to_usd_with_rate(self):
        fx = _FakeFx({("USD", "EUR"): Decimal("0.9120")})
        currency, rate = await _resolve_trade_fx(fx, "USDT", _TS)
        assert currency == "USD"
        assert rate == Decimal("0.9120")
        # Resolved at the trade's execution date, anchored on USD.
        assert fx.calls == [(_TS.date(), "USD", "EUR")]

    @pytest.mark.asyncio
    async def test_eur_quote_is_passthrough_no_lookup(self):
        fx = _FakeFx({("USD", "EUR"): Decimal("0.9120")})
        currency, rate = await _resolve_trade_fx(fx, "EUR", _TS)
        assert currency == "EUR"
        assert rate is None
        assert fx.calls == []  # never queries for the home currency

    @pytest.mark.asyncio
    async def test_missing_rate_falls_back_to_eur(self):
        # USD recognised, but no history for that date -> must NOT mislabel as USD.
        fx = _FakeFx({("USD", "EUR"): None})
        currency, rate = await _resolve_trade_fx(fx, "USDC", _TS)
        assert currency == "EUR"
        assert rate is None

    @pytest.mark.asyncio
    async def test_crypto_quote_falls_back_to_eur(self):
        fx = _FakeFx({("USD", "EUR"): Decimal("0.9120")})
        currency, rate = await _resolve_trade_fx(fx, "BTC", _TS)
        assert currency == "EUR"
        assert rate is None
        assert fx.calls == []  # crypto quote never reaches the FX service

    @pytest.mark.asyncio
    async def test_none_quote_falls_back_to_eur(self):
        fx = _FakeFx({})
        currency, rate = await _resolve_trade_fx(fx, None, _TS)
        assert currency == "EUR"
        assert rate is None

    @pytest.mark.asyncio
    async def test_no_fx_service_falls_back_to_eur(self):
        currency, rate = await _resolve_trade_fx(None, "USDT", _TS)
        assert currency == "EUR"
        assert rate is None

    @pytest.mark.asyncio
    async def test_gbp_quote_resolves_directly(self):
        fx = _FakeFx({("GBP", "EUR"): Decimal("1.16")})
        currency, rate = await _resolve_trade_fx(fx, "GBP", _TS)
        assert currency == "GBP"
        assert rate == Decimal("1.16")
