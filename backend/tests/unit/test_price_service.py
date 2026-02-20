"""Tests for price service with mocked HTTP and Redis dependencies.

Covers: get_crypto_price, get_stock_price, caching behavior, error handling,
stablecoin detection, forex rate fetching, and CoinGecko ID search.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.price_service import PriceService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis.hgetall.return_value = {}
    redis.get.return_value = None
    return redis


@pytest.fixture
def price_service(mock_redis):
    """Create a PriceService with mocked Redis and HTTP client."""
    with patch("app.services.price_service.settings") as mock_settings:
        mock_settings.REDIS_HOST = "localhost"
        mock_settings.REDIS_PORT = 6379
        mock_settings.COINGECKO_API_KEY = None
        with patch("app.services.price_service.Redis", return_value=mock_redis):
            svc = PriceService()
            svc.redis = mock_redis
            return svc


# ---------------------------------------------------------------------------
# Stablecoin detection
# ---------------------------------------------------------------------------
class TestStablecoinDetection:
    """Tests for the is_stablecoin class method."""

    def test_usdt_is_stablecoin(self):
        assert PriceService.is_stablecoin("USDT") is True

    def test_usdc_is_stablecoin(self):
        assert PriceService.is_stablecoin("USDC") is True

    def test_dai_is_stablecoin(self):
        assert PriceService.is_stablecoin("DAI") is True

    def test_btc_is_not_stablecoin(self):
        assert PriceService.is_stablecoin("BTC") is False

    def test_eth_is_not_stablecoin(self):
        assert PriceService.is_stablecoin("ETH") is False

    def test_case_insensitive(self):
        assert PriceService.is_stablecoin("usdt") is True
        assert PriceService.is_stablecoin("Usdc") is True

    def test_eurt_is_stablecoin(self):
        assert PriceService.is_stablecoin("EURT") is True

    def test_empty_string_is_not_stablecoin(self):
        assert PriceService.is_stablecoin("") is False


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------
class TestCacheKey:
    """Tests for _get_cache_key."""

    def test_crypto_cache_key(self, price_service):
        key = price_service._get_cache_key("crypto", "btc")
        assert key == "price:crypto:BTC"

    def test_stock_cache_key(self, price_service):
        key = price_service._get_cache_key("stock", "aapl")
        assert key == "price:stock:AAPL"


# ---------------------------------------------------------------------------
# Cache hit / miss behavior
# ---------------------------------------------------------------------------
class TestCacheBehavior:
    """Tests for cache hit and cache miss scenarios."""

    def test_cache_hit_returns_cached_data(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {
            "price": "45000.50",
            "change_24h": "500.0",
            "change_percent_24h": "1.12",
            "volume_24h": "1000000",
            "market_cap": "850000000000",
            "last_updated": "2026-01-01T00:00:00",
        }

        result = price_service._get_cached_price("crypto", "BTC")

        assert result is not None
        assert result["price"] == Decimal("45000.50")
        assert result["change_24h"] == 500.0
        assert result["change_percent_24h"] == 1.12

    def test_cache_miss_returns_none(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = price_service._get_cached_price("crypto", "BTC")
        assert result is None

    def test_cache_redis_error_returns_none(self, price_service, mock_redis):
        mock_redis.hgetall.side_effect = Exception("Redis connection error")
        result = price_service._get_cached_price("crypto", "BTC")
        assert result is None

    def test_cache_price_stores_in_redis(self, price_service, mock_redis):
        data = {
            "price": Decimal("45000.50"),
            "change_24h": 500.0,
            "change_percent_24h": 1.12,
            "volume_24h": 1000000,
            "market_cap": 850000000000,
        }
        price_service._cache_price("crypto", "BTC", data, 60)

        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once_with("price:crypto:BTC", 60)

    def test_cache_price_redis_error_no_raise(self, price_service, mock_redis):
        """Cache write failures should be silently ignored."""
        mock_redis.hset.side_effect = Exception("Redis write error")
        data = {"price": Decimal("100"), "change_24h": 0, "change_percent_24h": 0, "volume_24h": 0, "market_cap": 0}
        # Should not raise
        price_service._cache_price("crypto", "BTC", data, 60)


# ---------------------------------------------------------------------------
# get_crypto_price
# ---------------------------------------------------------------------------
class TestGetCryptoPrice:
    """Tests for get_crypto_price method."""

    @pytest.mark.asyncio
    async def test_returns_cached_result_if_available(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {
            "price": "45000.00",
            "change_24h": "100",
            "change_percent_24h": "0.5",
            "volume_24h": "999",
            "market_cap": "800000",
            "last_updated": "2026-01-01T00:00:00",
        }

        result = await price_service.get_crypto_price("BTC")
        assert result is not None
        assert result["price"] == Decimal("45000.00")

    @pytest.mark.asyncio
    async def test_fetches_from_coingecko(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "bitcoin": {
                "eur": 44000,
                "eur_24h_change": -200,
                "eur_24h_vol": 5000000,
                "eur_market_cap": 800000000,
            }
        }

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=mock_response)

        result = await price_service.get_crypto_price("BTC")
        assert result is not None
        assert result["price"] == Decimal("44000")

    @pytest.mark.asyncio
    async def test_fallback_to_cryptocompare(self, price_service, mock_redis):
        """When CoinGecko fails, should fall back to CryptoCompare."""
        mock_redis.hgetall.return_value = {}

        coingecko_response = MagicMock()
        coingecko_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=MagicMock()
        )

        cryptocompare_response = MagicMock()
        cryptocompare_response.status_code = 200
        cryptocompare_response.raise_for_status = MagicMock()
        cryptocompare_response.json.return_value = {
            "RAW": {
                "BTC": {
                    "EUR": {
                        "PRICE": 43500,
                        "CHANGE24HOUR": -100,
                        "CHANGEPCT24HOUR": -0.23,
                        "VOLUME24HOUR": 4000000,
                        "MKTCAP": 790000000,
                    }
                }
            }
        }

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First calls: CoinGecko search + price (both fail)
                return coingecko_response
            return cryptocompare_response

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(side_effect=mock_get)

        result = await price_service.get_crypto_price("BTC")
        assert result is not None
        assert result["price"] == Decimal("43500")

    @pytest.mark.asyncio
    async def test_stablecoin_fallback_when_apis_fail(self, price_service, mock_redis):
        """Stablecoins should fall back to forex rate when APIs fail."""
        mock_redis.hgetall.return_value = {}

        error_response = MagicMock()
        error_response.raise_for_status.side_effect = Exception("API error")

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=error_response)

        # Mock the forex fallback
        price_service._stablecoin_price_eur = AsyncMock(return_value=Decimal("0.92"))

        result = await price_service.get_crypto_price("USDT")
        assert result is not None
        assert result["price"] == Decimal("0.92")

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_symbol_when_all_fail(self, price_service, mock_redis):
        """Non-stablecoin with all API failures should return None."""
        mock_redis.hgetall.return_value = {}

        error_response = MagicMock()
        error_response.raise_for_status.side_effect = Exception("API error")

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=error_response)
        price_service._search_coingecko_id = AsyncMock(return_value=None)

        result = await price_service.get_crypto_price("UNKNOWNCOIN")
        assert result is None


# ---------------------------------------------------------------------------
# get_stock_price
# ---------------------------------------------------------------------------
class TestGetStockPrice:
    """Tests for get_stock_price method."""

    @pytest.mark.asyncio
    async def test_returns_cached_result(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {
            "price": "175.50",
            "change_24h": "2.5",
            "change_percent_24h": "1.44",
            "volume_24h": "50000000",
            "market_cap": "0",
            "last_updated": "2026-01-01T00:00:00",
        }

        result = await price_service.get_stock_price("AAPL")
        assert result is not None
        assert result["price"] == Decimal("175.50")

    @pytest.mark.asyncio
    async def test_fetches_from_yahoo_finance(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 180.25,
                            "previousClose": 178.00,
                            "regularMarketVolume": 45000000,
                        }
                    }
                ]
            }
        }

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=mock_response)

        result = await price_service.get_stock_price("AAPL")
        assert result is not None
        assert result["price"] == Decimal("180.25")
        assert result["change_24h"] == pytest.approx(2.25)
        assert result["change_percent_24h"] == pytest.approx(2.25 / 178.0 * 100, rel=1e-3)

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {}

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        result = await price_service.get_stock_price("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_symbol_returns_none(self, price_service, mock_redis):
        mock_redis.hgetall.return_value = {}

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=mock_response)

        result = await price_service.get_stock_price("INVALID_SYMBOL_XYZ")
        assert result is None


# ---------------------------------------------------------------------------
# get_price (generic dispatcher)
# ---------------------------------------------------------------------------
class TestGetPrice:
    """Tests for the generic get_price dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatches_crypto(self, price_service):
        price_service.get_crypto_price = AsyncMock(return_value={"price": Decimal("100")})
        result = await price_service.get_price("BTC", "crypto")
        price_service.get_crypto_price.assert_called_once_with("BTC", "eur")
        assert result["price"] == Decimal("100")

    @pytest.mark.asyncio
    async def test_dispatches_stock(self, price_service):
        price_service.get_stock_price = AsyncMock(return_value={"price": Decimal("150")})
        result = await price_service.get_price("AAPL", "stock")
        price_service.get_stock_price.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_dispatches_etf(self, price_service):
        price_service.get_stock_price = AsyncMock(return_value={"price": Decimal("50")})
        result = await price_service.get_price("SPY", "etf")
        price_service.get_stock_price.assert_called_once_with("SPY")

    @pytest.mark.asyncio
    async def test_dispatches_real_estate(self, price_service):
        price_service.get_real_estate_price = AsyncMock(return_value=None)
        result = await price_service.get_price("PROP1", "real_estate")
        price_service.get_real_estate_price.assert_called_once_with("PROP1")

    @pytest.mark.asyncio
    async def test_unknown_type_returns_none(self, price_service):
        result = await price_service.get_price("X", "unknown_type")
        assert result is None


# ---------------------------------------------------------------------------
# CoinGecko ID search
# ---------------------------------------------------------------------------
class TestSearchCoingeckoId:
    """Tests for _search_coingecko_id."""

    @pytest.mark.asyncio
    async def test_known_symbol_from_static_map(self, price_service):
        result = await price_service._search_coingecko_id("BTC")
        assert result == "bitcoin"

    @pytest.mark.asyncio
    async def test_known_symbol_case_insensitive(self, price_service):
        result = await price_service._search_coingecko_id("btc")
        assert result == "bitcoin"

    @pytest.mark.asyncio
    async def test_dynamic_cache_hit(self, price_service):
        price_service._dynamic_symbol_cache["NEWCOIN"] = "new-coin-id"
        result = await price_service._search_coingecko_id("NEWCOIN")
        assert result == "new-coin-id"

    @pytest.mark.asyncio
    async def test_redis_cached_id(self, price_service, mock_redis):
        mock_redis.get.return_value = "cached-coin-id"
        # Use a symbol not in static or dynamic maps
        result = await price_service._search_coingecko_id("XCOIN")
        assert result == "cached-coin-id"

    @pytest.mark.asyncio
    async def test_api_search_fallback(self, price_service, mock_redis):
        mock_redis.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "coins": [
                {"id": "wrong-coin", "symbol": "WRG"},
                {"id": "correct-coin", "symbol": "NEWCOIN2"},
            ]
        }

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=mock_response)

        result = await price_service._search_coingecko_id("NEWCOIN2")
        assert result == "correct-coin"
        # Should be saved to dynamic cache
        assert price_service._dynamic_symbol_cache["NEWCOIN2"] == "correct-coin"


# ---------------------------------------------------------------------------
# Forex rate
# ---------------------------------------------------------------------------
class TestGetForexRate:
    """Tests for get_forex_rate."""

    @pytest.mark.asyncio
    async def test_returns_cached_forex(self, price_service, mock_redis):
        mock_redis.get.return_value = "0.92"
        result = await price_service.get_forex_rate("USD", "EUR")
        assert result == Decimal("0.92")

    @pytest.mark.asyncio
    async def test_fetches_live_rate(self, price_service, mock_redis):
        mock_redis.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"rates": {"EUR": 0.91}}

        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(return_value=mock_response)

        result = await price_service.get_forex_rate("USD", "EUR")
        assert result == Decimal("0.91")

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, price_service, mock_redis):
        mock_redis.get.return_value = None
        price_service.http_client = AsyncMock()
        price_service.http_client.get = AsyncMock(side_effect=Exception("Network error"))

        result = await price_service.get_forex_rate("USD", "EUR")
        assert result is None


# ---------------------------------------------------------------------------
# Symbol map coverage
# ---------------------------------------------------------------------------
class TestSymbolMap:
    """Tests for the SYMBOL_MAP static data."""

    def test_major_coins_present(self):
        for sym in ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"]:
            assert sym in PriceService.SYMBOL_MAP

    def test_stablecoins_in_map(self):
        assert "USDC" in PriceService.SYMBOL_MAP
        assert "USDT" in PriceService.SYMBOL_MAP

    def test_all_values_are_strings(self):
        for sym, coin_id in PriceService.SYMBOL_MAP.items():
            assert isinstance(sym, str)
            assert isinstance(coin_id, str)
            assert len(coin_id) > 0
