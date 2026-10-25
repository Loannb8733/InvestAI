import math
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.market_data.prices.quote import PriceQuote

FROZEN_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
HISTORY_DAYS = 420

ASSETS = [
    ("BTC", "crypto", "Binance", "60000"),
    ("ETH", "crypto", "Kraken", "3000"),
    ("SOL", "crypto", "Tangem", "150"),
    ("ARB", "crypto", "Binance", "0.8"),
    ("UNI", "crypto", "Kraken", "9"),
    ("USDC", "crypto", "Binance", "0.92"),
    ("DOGE", "crypto", "Binance", "0.15"),
    ("AAPL", "stock", "Trade Republic", "200"),
]
QUOTES = {symbol: Decimal(price) for symbol, _, _, price in ASSETS}
TRANSACTIONS = [
    ("BTC", "buy", "0.5", "30000", "10", "2025-01-10T10:00:00Z"),
    ("BTC", "buy", "0.25", "50000", "5", "2025-08-01T10:00:00Z"),
    ("BTC", "sell", "0.1", "70000", "7", "2025-11-15T10:00:00Z"),
    ("ETH", "buy", "4", "2000", "4", "2025-02-15T10:00:00Z"),
    ("ETH", "sell", "1", "3500", "3", "2026-03-01T10:00:00Z"),
    ("SOL", "buy", "50", "100", "2", "2025-04-01T10:00:00Z"),
    ("ARB", "buy", "1000", "1.2", "1", "2025-03-01T10:00:00Z"),
    ("UNI", "buy", "200", "7", "1", "2025-06-01T10:00:00Z"),
    ("USDC", "buy", "2000", "0.93", "0", "2025-01-05T10:00:00Z"),
    ("DOGE", "buy", "10000", "0.1", "1", "2025-09-01T10:00:00Z"),
    ("AAPL", "buy", "20", "170", "1", "2025-05-20T10:00:00Z"),
]
SERIES = {
    "BTC": (40000, 0.0012, 0.08, 23, 0.0),
    "ETH": (2200, 0.0009, 0.11, 17, 1.0),
    "SOL": (90, 0.0015, 0.15, 13, 2.0),
    "ARB": (1.1, -0.0008, 0.2, 11, 0.3),
    "UNI": (7, 0.0004, 0.18, 19, 1.7),
    "USDC": (0.92, 0.0, 0.002, 7, 0.0),
    "DOGE": (0.1, 0.001, 0.25, 9, 2.4),
    "AAPL": (165, 0.0004, 0.04, 31, 0.5),
    "PAXG": (2000, 0.0003, 0.02, 41, 1.5),
    "SPY": (480, 0.0003, 0.03, 29, 0.7),
    "^GSPC": (5000, 0.0003, 0.03, 29, 0.6),
}
TARGETS = {"L1": 0.5, "L2": 0.1, "DeFi": 0.1, "Stable": 0.2, "Meme": 0.1}


def _price(symbol: str, day: int) -> Decimal:
    base, drift, amplitude, period, phase = SERIES[symbol]
    value = base * (1 + drift * day) * (1 + amplitude * math.sin(day / period + phase))
    return Decimal(str(round(value, 6)))


async def fake_quotes(symbols: Iterable[str], currency: str = "EUR") -> dict[str, PriceQuote]:
    return {s.upper(): PriceQuote(price=QUOTES[s.upper()]) for s in symbols if s.upper() in QUOTES}


async def fake_quote(symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote | None:
    price = QUOTES.get(symbol.upper())
    return PriceQuote(price=price) if price is not None else None


async def seed_history(db: AsyncSession) -> None:
    start = FROZEN_NOW.date() - timedelta(days=HISTORY_DAYS)
    for symbol in SERIES:
        for day in range(HISTORY_DAYS + 1):
            moment: date = start + timedelta(days=day)
            db.add(AssetPriceHistory(symbol=symbol, price_date=moment, price_eur=_price(symbol, day), source="test"))
    await db.commit()


async def seed_portfolio(client: AsyncClient, headers: dict[str, str]) -> None:
    portfolio = await client.post("/api/v1/portfolios", json={"name": "Rapports"}, headers=headers)
    assert portfolio.status_code == 201, portfolio.text
    portfolio_id = portfolio.json()["id"]
    asset_ids: dict[str, str] = {}
    for symbol, kind, exchange, price in ASSETS:
        body = {
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "asset_type": kind,
            "exchange": exchange,
            "current_price": price,
        }
        asset = await client.post("/api/v1/assets", json=body, headers=headers)
        assert asset.status_code == 201, asset.text
        asset_ids[symbol] = asset.json()["id"]
    for symbol, kind, quantity, price, fee, executed_at in TRANSACTIONS:
        body = {
            "asset_id": asset_ids[symbol],
            "transaction_type": kind,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "currency": "EUR",
            "executed_at": executed_at,
            "exchange": next(e for s, _, e, _ in ASSETS if s == symbol),
        }
        tx = await client.post("/api/v1/transactions", json=body, headers=headers)
        assert tx.status_code == 201, tx.text
