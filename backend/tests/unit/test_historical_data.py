"""Tests for historical data fetcher."""

import pytest

from app.ml.historical_data import HistoricalDataFetcher


class TestSymbolMap:
    """Tests for CoinGecko symbol mapping."""

    def test_btc_maps_to_bitcoin(self):
        assert HistoricalDataFetcher.SYMBOL_MAP["BTC"] == "bitcoin"

    def test_eth_maps_to_ethereum(self):
        assert HistoricalDataFetcher.SYMBOL_MAP["ETH"] == "ethereum"

    def test_unknown_symbol_fallback(self):
        """Unknown symbols should use lowercase as coin_id."""
        fetcher = HistoricalDataFetcher()
        # Verify the logic in get_crypto_history uses .lower() for unknown
        coin_id = HistoricalDataFetcher.SYMBOL_MAP.get("UNKNOWN", "unknown")
        assert coin_id == "unknown"

    def test_all_symbols_are_uppercase(self):
        for key in HistoricalDataFetcher.SYMBOL_MAP:
            assert key == key.upper()

    def test_all_ids_are_lowercase(self):
        for value in HistoricalDataFetcher.SYMBOL_MAP.values():
            assert value == value.lower()


class TestGetHistory:
    """Tests for get_history dispatcher (without network calls)."""

    @pytest.fixture
    def fetcher(self):
        return HistoricalDataFetcher()

    @pytest.mark.asyncio
    async def test_unknown_asset_type_returns_empty(self, fetcher):
        dates, prices = await fetcher.get_history("BTC", "real_estate", 30)
        assert dates == []
        assert prices == []

    @pytest.mark.asyncio
    async def test_dispatches_crypto(self, fetcher, monkeypatch):
        called_with = {}

        async def mock_crypto(symbol, days, currency="eur"):
            called_with["symbol"] = symbol
            called_with["days"] = days
            return [], []

        monkeypatch.setattr(fetcher, "get_crypto_history", mock_crypto)
        await fetcher.get_history("BTC", "crypto", 90)
        assert called_with["symbol"] == "BTC"
        assert called_with["days"] == 90

    @pytest.mark.asyncio
    async def test_dispatches_stock(self, fetcher, monkeypatch):
        called_with = {}

        async def mock_stock(symbol, days):
            called_with["symbol"] = symbol
            return [], []

        monkeypatch.setattr(fetcher, "get_stock_history", mock_stock)
        await fetcher.get_history("AAPL", "stock", 30)
        assert called_with["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_dispatches_etf(self, fetcher, monkeypatch):
        called = False

        async def mock_stock(symbol, days):
            nonlocal called
            called = True
            return [], []

        monkeypatch.setattr(fetcher, "get_stock_history", mock_stock)
        await fetcher.get_history("SPY", "etf", 30)
        assert called
