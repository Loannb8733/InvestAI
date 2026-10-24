import pytest

from app.domains.market_data.prices.service import price_feed
from tests.reports.seed import fake_quote, fake_quotes


@pytest.fixture
def live_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(price_feed, "crypto", fake_quotes)
    monkeypatch.setattr(price_feed, "stocks", fake_quotes)
    monkeypatch.setattr(price_feed, "quote", fake_quote)
