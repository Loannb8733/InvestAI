"""Unit tests for historical FX resolution (FIN-01).

Pins the forward-fill date logic and rate inversion. Pure functions: no DB/HTTP/Docker.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.fx_history import build_sorted_rates, invert_rate, resolve_rate


@pytest.fixture
def rates():
    # Mon 2024-01-15 .. Fri 2024-01-19 (business days only; weekend intentionally absent).
    return build_sorted_rates(
        {
            date(2024, 1, 15): Decimal("0.9100"),
            date(2024, 1, 16): Decimal("0.9150"),
            date(2024, 1, 17): Decimal("0.9120"),
            date(2024, 1, 18): Decimal("0.9180"),
            date(2024, 1, 19): Decimal("0.9200"),
        }
    )


class TestResolveRate:
    def test_exact_business_day(self, rates):
        assert resolve_rate(date(2024, 1, 17), rates) == Decimal("0.9120")

    def test_saturday_forward_fills_from_friday(self, rates):
        # Sat 2024-01-20 has no ECB fix -> use Fri 2024-01-19.
        assert resolve_rate(date(2024, 1, 20), rates) == Decimal("0.9200")

    def test_sunday_forward_fills_from_friday(self, rates):
        assert resolve_rate(date(2024, 1, 21), rates) == Decimal("0.9200")

    def test_future_date_uses_latest_known(self, rates):
        # Beyond the last known date -> latest available (caller decides staleness).
        assert resolve_rate(date(2024, 6, 1), rates) == Decimal("0.9200")

    def test_before_history_returns_none(self, rates):
        # Must not fabricate a rate before history begins.
        assert resolve_rate(date(2024, 1, 14), rates) is None

    def test_empty_returns_none(self):
        assert resolve_rate(date(2024, 1, 15), []) is None

    def test_first_day_exact(self, rates):
        assert resolve_rate(date(2024, 1, 15), rates) == Decimal("0.9100")


class TestBuildSortedRates:
    def test_sorts_ascending(self):
        out = build_sorted_rates({date(2024, 1, 3): 1.0, date(2024, 1, 1): 2.0, date(2024, 1, 2): 3.0})
        assert [d for d, _ in out] == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

    def test_coerces_to_decimal(self):
        out = build_sorted_rates({date(2024, 1, 1): 0.92})
        assert isinstance(out[0][1], Decimal)


class TestInvertRate:
    def test_eur_usd_to_usd_eur(self):
        # EUR/USD 1.09 (USD per EUR) -> ~0.9174 (EUR per USD).
        inv = invert_rate(Decimal("1.09"))
        assert inv == pytest.approx(Decimal("0.917431"), abs=Decimal("1e-6"))

    def test_roundtrip(self):
        assert invert_rate(invert_rate(Decimal("1.09"))) == pytest.approx(Decimal("1.09"), abs=Decimal("1e-9"))

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            invert_rate(Decimal("0"))
