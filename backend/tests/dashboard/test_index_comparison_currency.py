from collections.abc import Iterable
from decimal import Decimal
from typing import Any

import pytest

from app.domains.dashboard import feed
from app.domains.market_data.prices.quote import PriceQuote


async def test_index_prices_follow_the_user_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    async def crypto(symbols: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
        asked.append(currency)
        return {symbol: PriceQuote(price=Decimal("110")) for symbol in symbols}

    async def changes(symbols: dict[str, list[str]], days: int) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(feed.price_feed, "crypto", crypto)
    monkeypatch.setattr(feed.metrics_service, "fetch_period_changes", changes)
    indices = await feed.get_index_comparison(30, "USD")
    assert asked == ["USD"]
    assert [index.price for index in indices] == [110.0, 110.0, 110.0]
