import json
from collections.abc import Iterable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.market_data.prices import tasks
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from tests.conftest import TestSessionLocal


class _RecordingClient:
    def __init__(self, fails: bool = False) -> None:
        self.fails = fails
        self.messages: list[dict[str, object]] = []

    def publish(self, channel: str, message: str) -> None:
        if self.fails:
            raise ConnectionError("redis injoignable")
        self.messages.append(json.loads(message))


async def _quotes(symbols: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
    return {symbol.upper(): PriceQuote(price=Decimal("10"), change_percent_24h=1.0) for symbol in symbols}


async def _hold(db: AsyncSession, user: User, holdings: Iterable[tuple[str, AssetType]]) -> None:
    portfolio = Portfolio(user_id=user.id, name="P")
    db.add(portfolio)
    await db.flush()
    for symbol, kind in holdings:
        db.add(Asset(portfolio_id=portfolio.id, symbol=symbol, name=symbol, asset_type=kind, quantity=1))
    await db.commit()


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> _RecordingClient:
    client = _RecordingClient()
    monkeypatch.setattr(tasks, "session_factory", TestSessionLocal)
    monkeypatch.setattr(tasks, "_publisher", client)
    monkeypatch.setattr(price_feed, "crypto", _quotes)
    monkeypatch.setattr(price_feed, "stocks", _quotes)
    return client


async def test_published_prices_carry_their_currency(
    db_session: AsyncSession, regular_user: User, publisher: _RecordingClient
) -> None:
    await _hold(db_session, regular_user, [("BTC", AssetType.CRYPTO), ("AAPL", AssetType.STOCK)])
    await tasks.publish_crypto_prices()
    await tasks.publish_stock_prices()
    assert [message["currency"] for message in publisher.messages] == ["EUR", "EUR"]


async def test_a_failed_publication_is_not_counted(
    db_session: AsyncSession, regular_user: User, publisher: _RecordingClient
) -> None:
    publisher.fails = True
    await _hold(db_session, regular_user, [("BTC", AssetType.CRYPTO), ("AAPL", AssetType.STOCK)])
    assert (await tasks.publish_crypto_prices())["updated"] == 0
    assert (await tasks.publish_stock_prices())["updated"] == 0


async def test_stocks_and_etfs_are_priced_in_one_call(
    db_session: AsyncSession, regular_user: User, publisher: _RecordingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    async def stocks(tickers: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
        calls.append(sorted(tickers))
        return await _quotes(tickers)

    monkeypatch.setattr(price_feed, "stocks", stocks)
    await _hold(
        db_session, regular_user, [("AAPL", AssetType.STOCK), ("MSFT", AssetType.STOCK), ("SPY", AssetType.ETF)]
    )
    result = await tasks.publish_stock_prices()
    assert calls == [["AAPL", "MSFT", "SPY"]]
    assert result["updated"] == 3
    assert {(m["symbol"], m["asset_type"]) for m in publisher.messages} == {
        ("AAPL", "stock"),
        ("MSFT", "stock"),
        ("SPY", "etf"),
    }


async def test_listed_symbols_are_the_first_in_alphabetical_order(
    db_session: AsyncSession, regular_user: User, publisher: _RecordingClient
) -> None:
    symbols = [f"C{index:02d}" for index in range(25)]
    await _hold(db_session, regular_user, [(symbol, AssetType.CRYPTO) for symbol in reversed(symbols)])
    assert (await tasks.publish_crypto_prices())["symbols"] == symbols[: tasks.LISTED_SYMBOLS]
