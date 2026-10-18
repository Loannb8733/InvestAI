"""Unit tests for historical FX resolution (FIN-01).

Pins the forward-fill date logic and rate inversion. Pure functions: no DB/HTTP/Docker.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.fx_history import resolve_rate


@pytest.fixture
def rates():
    # Mon 2024-01-15 .. Fri 2024-01-19 (business days only; weekend intentionally absent).
    return [
        (date(2024, 1, 15), Decimal("0.9100")),
        (date(2024, 1, 16), Decimal("0.9150")),
        (date(2024, 1, 17), Decimal("0.9120")),
        (date(2024, 1, 18), Decimal("0.9180")),
        (date(2024, 1, 19), Decimal("0.9200")),
    ]


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
