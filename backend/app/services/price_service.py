"""Price fetching service for various asset types."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import httpx
from redis import Redis

from app.core.config import settings


class PriceService:
    """Service for fetching and caching asset prices."""

    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com/data"
    YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    # Cache TTL in seconds
    CACHE_TTL_CRYPTO = 60  # 1 minute
    CACHE_TTL_STOCK = 300  # 5 minutes
    CACHE_TTL_FOREX = 3600  # 1 hour

    # Unified symbol map for CoinGecko IDs
    SYMBOL_MAP = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LINK": "chainlink",
        "AVAX": "avalanche-2",
        "UNI": "uniswap",
        "ATOM": "cosmos",
        "LTC": "litecoin",
        "ETC": "ethereum-classic",
        "PEPE": "pepe",
        "PAXG": "pax-gold",
        "SHIB": "shiba-inu",
        "ARB": "arbitrum",
        "OP": "optimism",
        "APT": "aptos",
        "INJ": "injective-protocol",
        "NEAR": "near",
        "FTM": "fantom",
        "ALGO": "algorand",
        "XLM": "stellar",
        "VET": "vechain",
        "FIL": "filecoin",
        "HBAR": "hedera-hashgraph",
        "ICP": "internet-computer",
        "SAND": "the-sandbox",
        "MANA": "decentraland",
        "AXS": "axie-infinity",
        "AAVE": "aave",
        "GRT": "the-graph",
        "CRV": "curve-dao-token",
        "MKR": "maker",
        "SNX": "synthetix-network-token",
        "COMP": "compound-governance-token",
        "SUSHI": "sushi",
        "YFI": "yearn-finance",
        "1INCH": "1inch",
        "ENJ": "enjincoin",
        "CHZ": "chiliz",
        "BAT": "basic-attention-token",
        "ZRX": "0x",
        "OCEAN": "ocean-protocol",
        "RNDR": "render-token",
        "IMX": "immutable-x",
        "LDO": "lido-dao",
        "RPL": "rocket-pool",
        "CRO": "crypto-com-chain",
        "KAVA": "kava",
        "RUNE": "thorchain",
        "ZEC": "zcash",
        "XMR": "monero",
        "DASH": "dash",
        "QTUM": "qtum",
        "ZIL": "zilliqa",
        "ENS": "ethereum-name-service",
        "GALA": "gala",
        "FLOW": "flow",
        "THETA": "theta-token",
        "EGLD": "elrond-erd-2",
        "XTZ": "tezos",
        "EOS": "eos",
        "NEO": "neo",
        "IOTA": "iota",
        "KSM": "kusama",
        "WAVES": "waves",
        "CELO": "celo",
        "ONE": "harmony",
        "ANKR": "ankr",
        "AUDIO": "audius",
        "BAND": "band-protocol",
        "STORJ": "storj",
        "SKL": "skale",
        "CTSI": "cartesi",
        "NMR": "numeraire",
        "OGN": "origin-protocol",
        "CELR": "celer-network",
        "SPELL": "spell-token",
        "JASMY": "jasmycoin",
        "TRX": "tron",
        "SUI": "sui",
        "SEI": "sei-network",
        "TIA": "celestia",
        "JUP": "jupiter-exchange-solana",
        "WIF": "dogwifcoin",
        "BONK": "bonk",
        "FLOKI": "floki",
        "BOME": "book-of-meme",
        "WLD": "worldcoin-wld",
        "STRK": "starknet",
        "BLUR": "blur",
        "PYTH": "pyth-network",
        "JTO": "jito-governance-token",
        "ORDI": "ordi",
        "STX": "stacks",
        "INS": "insure-defi",
        "TAO": "bittensor",
        "CGPT": "chaingpt",
        "USDG": "first-digital-usd",
        "FET": "fetch-ai",
        "USDC": "usd-coin",
        "USDT": "tether",
    }

    def __init__(self):
        self.redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
        # CoinGecko API key (optional, for higher rate limits)
        self.coingecko_api_key = getattr(settings, 'COINGECKO_API_KEY', None) or None

        # Build headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        # Add API key header if available
        if self.coingecko_api_key:
            headers["x-cg-demo-api-key"] = self.coingecko_api_key

        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)

        # Dynamic symbol cache (discovered from API)
        self._dynamic_symbol_cache: Dict[str, str] = {}

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def _search_coingecko_id(self, symbol: str) -> Optional[str]:
        """Search CoinGecko for the correct coin ID by symbol."""
        symbol_upper = symbol.upper()

        # Check static map first
        if symbol_upper in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol_upper]

        # Check dynamic cache
        if symbol_upper in self._dynamic_symbol_cache:
            return self._dynamic_symbol_cache[symbol_upper]

        # Check Redis cache for discovered ID
        cache_key = f"coingecko_id:{symbol_upper}"
        try:
            cached_id = self.redis.get(cache_key)
            if cached_id:
                self._dynamic_symbol_cache[symbol_upper] = cached_id
                return cached_id
        except Exception:
            pass

        # Search CoinGecko API
        try:
            response = await self.http_client.get(
                f"{self.COINGECKO_BASE_URL}/search",
                params={"query": symbol_upper},
            )
            response.raise_for_status()
            data = response.json()

            coins = data.get("coins", [])

            # Find exact symbol match (case insensitive)
            for coin in coins:
                if coin.get("symbol", "").upper() == symbol_upper:
                    coin_id = coin.get("id")
                    if coin_id:
                        # Cache the discovered ID for 7 days
                        try:
                            self.redis.setex(cache_key, 604800, coin_id)
                        except Exception:
                            pass
                        self._dynamic_symbol_cache[symbol_upper] = coin_id
                        print(f"Discovered CoinGecko ID for {symbol_upper}: {coin_id}")
                        return coin_id

            print(f"No exact match found on CoinGecko for symbol: {symbol_upper}")

        except Exception as e:
            print(f"Error searching CoinGecko for {symbol}: {e}")

        return None

    def _get_cache_key(self, asset_type: str, symbol: str) -> str:
        """Generate cache key for price."""
        return f"price:{asset_type}:{symbol.upper()}"

    def _get_cached_price(self, asset_type: str, symbol: str) -> Optional[Dict]:
        """Get price from Redis cache."""
        try:
            key = self._get_cache_key(asset_type, symbol)
            data = self.redis.hgetall(key)
            if data:
                return {
                    "price": Decimal(data["price"]),
                    "change_24h": float(data.get("change_24h", 0)),
                    "change_percent_24h": float(data.get("change_percent_24h", 0)),
                    "volume_24h": float(data.get("volume_24h", 0)),
                    "market_cap": float(data.get("market_cap", 0)),
                    "last_updated": data.get("last_updated"),
                }
        except Exception as e:
            print(f"Redis cache read error for {symbol}: {e}")
        return None

    def _cache_price(self, asset_type: str, symbol: str, data: Dict, ttl: int):
        """Cache price in Redis."""
        try:
            key = self._get_cache_key(asset_type, symbol)
            cache_data = {
                "price": str(data["price"]),
                "change_24h": str(data.get("change_24h", 0)),
                "change_percent_24h": str(data.get("change_percent_24h", 0)),
                "volume_24h": str(data.get("volume_24h", 0)),
                "market_cap": str(data.get("market_cap", 0)),
                "last_updated": datetime.utcnow().isoformat(),
            }
            self.redis.hset(key, mapping=cache_data)
            self.redis.expire(key, ttl)
        except Exception as e:
            print(f"Redis cache write error for {symbol}: {e}")

    # Stablecoins: peg currency (USD or EUR)
    STABLECOINS: Dict[str, str] = {
        "USDT": "USD",   # Tether
        "USDC": "USD",   # USD Coin
        "BUSD": "USD",   # Binance USD
        "DAI": "USD",    # Dai
        "TUSD": "USD",   # TrueUSD
        "USDP": "USD",   # Pax Dollar
        "GUSD": "USD",   # Gemini Dollar
        "FRAX": "USD",   # Frax
        "LUSD": "USD",   # Liquity USD
        "USDD": "USD",   # USDD
        "PYUSD": "USD",  # PayPal USD
        "FDUSD": "USD",  # First Digital USD
        "USDG": "USD",   # Global Dollar (Paxos)
        "EURT": "EUR",   # Euro Tether
        "EUROC": "EUR",  # Euro Coin
    }

    # Cached EUR/USD rate (refreshed via get_forex_rate)
    _eur_usd_rate: Optional[Decimal] = None
    _eur_usd_rate_ts: float = 0.0

    @classmethod
    def is_stablecoin(cls, symbol: str) -> bool:
        """Check if a symbol is a stablecoin."""
        return symbol.upper() in cls.STABLECOINS

    async def _get_eur_usd_rate(self) -> Decimal:
        """Get EUR/USD rate with 1h cache."""
        import time
        now = time.time()
        if self._eur_usd_rate and now - self._eur_usd_rate_ts < 3600:
            return self._eur_usd_rate
        rate = await self.get_forex_rate("USD", "EUR")
        if rate:
            PriceService._eur_usd_rate = rate
            PriceService._eur_usd_rate_ts = now
            return rate
        return Decimal("0.92")  # fallback

    async def _stablecoin_price_eur(self, symbol: str) -> Decimal:
        """Get stablecoin price in EUR using live forex rate."""
        peg = self.STABLECOINS.get(symbol.upper(), "USD")
        if peg == "EUR":
            return Decimal("1.00")
        rate = await self._get_eur_usd_rate()
        return rate  # 1 USD stablecoin = rate EUR

    async def get_crypto_price(self, symbol: str, currency: str = "eur") -> Optional[Dict]:
        """Fetch cryptocurrency price from CoinGecko or CryptoCompare fallback."""
        symbol_upper = symbol.upper()
        is_stablecoin = symbol_upper in self.STABLECOINS

        # Check cache first
        cached = self._get_cached_price("crypto", symbol)
        if cached:
            return cached

        # Try CoinGecko first - search for the correct ID
        try:
            coin_id = await self._search_coingecko_id(symbol)
            if not coin_id:
                # Fallback to lowercase symbol
                coin_id = symbol.lower()

            response = await self.http_client.get(
                f"{self.COINGECKO_BASE_URL}/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": currency,
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_market_cap": "true",
                },
            )
            response.raise_for_status()
            data = response.json()

            if coin_id in data:
                coin_data = data[coin_id]
                price = Decimal(str(coin_data.get(currency, 0)))
                # Only use if price is valid (> 0)
                if price > 0:
                    result = {
                        "price": price,
                        "change_24h": coin_data.get(f"{currency}_24h_change", 0) or 0,
                        "change_percent_24h": coin_data.get(f"{currency}_24h_change", 0) or 0,
                        "volume_24h": coin_data.get(f"{currency}_24h_vol", 0) or 0,
                        "market_cap": coin_data.get(f"{currency}_market_cap", 0) or 0,
                    }
                    self._cache_price("crypto", symbol, result, self.CACHE_TTL_CRYPTO)
                    return result

        except Exception as e:
            print(f"CoinGecko failed for {symbol}: {e}, trying CryptoCompare...")

        # Fallback to CryptoCompare
        try:
            response = await self.http_client.get(
                f"{self.CRYPTOCOMPARE_BASE_URL}/pricemultifull",
                params={
                    "fsyms": symbol.upper(),
                    "tsyms": currency.upper(),
                },
            )
            response.raise_for_status()
            data = response.json()

            raw_data = data.get("RAW", {}).get(symbol.upper(), {}).get(currency.upper(), {})
            if raw_data:
                price = Decimal(str(raw_data.get("PRICE", 0)))
                # Only use if price is valid (> 0)
                if price > 0:
                    result = {
                        "price": price,
                        "change_24h": raw_data.get("CHANGE24HOUR", 0) or 0,
                        "change_percent_24h": raw_data.get("CHANGEPCT24HOUR", 0) or 0,
                        "volume_24h": raw_data.get("VOLUME24HOUR", 0) or 0,
                        "market_cap": raw_data.get("MKTCAP", 0) or 0,
                    }
                    self._cache_price("crypto", symbol, result, self.CACHE_TTL_CRYPTO)
                    return result

        except Exception as e:
            print(f"CryptoCompare also failed for {symbol}: {e}")

        # Fallback to live forex rate for stablecoins if APIs failed
        if is_stablecoin:
            base_price = await self._stablecoin_price_eur(symbol_upper)
            if currency.lower() == "usd":
                base_price = Decimal("1.00")
            print(f"Using forex fallback price for stablecoin {symbol_upper}: {base_price}")
            result = {
                "price": base_price,
                "change_24h": 0,
                "change_percent_24h": 0,
                "volume_24h": 0,
                "market_cap": 0,
            }
            self._cache_price("crypto", symbol, result, self.CACHE_TTL_CRYPTO)
            return result

        return None

    async def get_stock_price(self, symbol: str) -> Optional[Dict]:
        """Fetch stock/ETF price from Yahoo Finance."""
        # Check cache first
        cached = self._get_cached_price("stock", symbol)
        if cached:
            return cached

        try:
            response = await self.http_client.get(
                f"{self.YAHOO_BASE_URL}/{symbol}",
                params={
                    "interval": "1d",
                    "range": "2d",
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            response.raise_for_status()
            data = response.json()

            chart = data.get("chart", {}).get("result", [{}])[0]
            meta = chart.get("meta", {})

            current_price = meta.get("regularMarketPrice", 0)
            previous_close = meta.get("previousClose", current_price)

            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close else 0

            result = {
                "price": Decimal(str(current_price)),
                "change_24h": change,
                "change_percent_24h": change_percent,
                "volume_24h": meta.get("regularMarketVolume", 0),
                "market_cap": 0,
            }
            self._cache_price("stock", symbol, result, self.CACHE_TTL_STOCK)
            return result

        except Exception as e:
            print(f"Error fetching stock price for {symbol}: {e}")

        return None

    async def get_real_estate_price(self, symbol: str) -> Optional[Dict]:
        """Get real estate price estimate.

        Uses EPRA Eurozone REIT ETF as a market proxy, or returns None
        (the asset's avg_buy_price will be used as fallback).
        """
        # Try European REIT ETF proxy for market direction
        for proxy in ["EPRE.PA", "IPRP.AS"]:
            result = await self.get_stock_price(proxy)
            if result and result.get("price", 0) > 0:
                return result
        return None

    async def get_price(self, symbol: str, asset_type: str, currency: str = "eur") -> Optional[Dict]:
        """Get price for any asset type."""
        if asset_type == "crypto":
            return await self.get_crypto_price(symbol, currency)
        elif asset_type in ["stock", "etf"]:
            return await self.get_stock_price(symbol)
        elif asset_type == "real_estate":
            return await self.get_real_estate_price(symbol)
        return None

    async def _fetch_from_cryptocompare(
        self, symbols: List[str], currency: str = "EUR"
    ) -> Dict[str, Dict]:
        """Fallback: Fetch prices from CryptoCompare API."""
        results = {}
        try:
            # CryptoCompare uses uppercase symbols directly
            symbols_str = ",".join([s.upper() for s in symbols])

            response = await self.http_client.get(
                f"{self.CRYPTOCOMPARE_BASE_URL}/pricemultifull",
                params={
                    "fsyms": symbols_str,
                    "tsyms": currency.upper(),
                },
            )
            response.raise_for_status()
            data = response.json()

            raw_data = data.get("RAW", {})
            for symbol, currency_data in raw_data.items():
                coin_data = currency_data.get(currency.upper(), {})
                if coin_data:
                    result = {
                        "price": Decimal(str(coin_data.get("PRICE", 0))),
                        "change_24h": coin_data.get("CHANGE24HOUR", 0) or 0,
                        "change_percent_24h": coin_data.get("CHANGEPCT24HOUR", 0) or 0,
                        "volume_24h": coin_data.get("VOLUME24HOUR", 0) or 0,
                        "market_cap": coin_data.get("MKTCAP", 0) or 0,
                    }
                    self._cache_price("crypto", symbol, result, self.CACHE_TTL_CRYPTO)
                    results[symbol.upper()] = result

        except Exception as e:
            print(f"Error fetching from CryptoCompare: {e}")

        return results

    async def get_multiple_crypto_prices(
        self, symbols: List[str], currency: str = "eur"
    ) -> Dict[str, Dict]:
        """Fetch multiple cryptocurrency prices at once."""
        results = {}

        # Check cache first
        uncached_symbols = []
        for symbol in symbols:
            cached = self._get_cached_price("crypto", symbol)
            if cached:
                results[symbol.upper()] = cached
            else:
                uncached_symbols.append(symbol)

        if not uncached_symbols:
            return results

        # Search for CoinGecko IDs for unknown symbols
        symbol_to_id = {}
        for symbol in uncached_symbols:
            coin_id = await self._search_coingecko_id(symbol)
            if coin_id:
                symbol_to_id[symbol.upper()] = coin_id
            else:
                symbol_to_id[symbol.upper()] = symbol.lower()

        # Try CoinGecko first
        try:
            coin_ids = list(symbol_to_id.values())

            response = await self.http_client.get(
                f"{self.COINGECKO_BASE_URL}/simple/price",
                params={
                    "ids": ",".join(coin_ids),
                    "vs_currencies": currency,
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_market_cap": "true",
                },
            )
            response.raise_for_status()
            data = response.json()

            # Reverse map to get original symbols (from both static and dynamic maps)
            id_to_symbol = {v: k for k, v in self.SYMBOL_MAP.items()}
            id_to_symbol.update({v: k for k, v in symbol_to_id.items()})

            for coin_id, coin_data in data.items():
                symbol = id_to_symbol.get(coin_id, coin_id.upper())
                result = {
                    "price": Decimal(str(coin_data.get(currency, 0))),
                    "change_24h": coin_data.get(f"{currency}_24h_change", 0) or 0,
                    "change_percent_24h": coin_data.get(f"{currency}_24h_change", 0) or 0,
                    "volume_24h": coin_data.get(f"{currency}_24h_vol", 0) or 0,
                    "market_cap": coin_data.get(f"{currency}_market_cap", 0) or 0,
                }
                self._cache_price("crypto", symbol, result, self.CACHE_TTL_CRYPTO)
                results[symbol.upper()] = result

        except Exception as e:
            print(f"CoinGecko failed: {e}, falling back to CryptoCompare...")

        # Check which symbols still don't have prices and try CryptoCompare
        missing_symbols = [s for s in uncached_symbols if s.upper() not in results]
        if missing_symbols:
            print(f"Trying CryptoCompare for missing symbols: {missing_symbols}")
            fallback_results = await self._fetch_from_cryptocompare(missing_symbols, currency)
            results.update(fallback_results)

        # Final fallback: use live forex rate for stablecoins that still have no price or price = 0
        for symbol in uncached_symbols:
            symbol_upper = symbol.upper()
            if symbol_upper not in results or results[symbol_upper].get("price", 0) == 0:
                if symbol_upper in self.STABLECOINS:
                    base_price = await self._stablecoin_price_eur(symbol_upper)
                    if currency.lower() == "usd":
                        base_price = Decimal("1.00")
                    print(f"Using forex fallback price for stablecoin {symbol_upper}: {base_price}")
                    results[symbol_upper] = {
                        "price": base_price,
                        "change_24h": 0,
                        "change_percent_24h": 0,
                        "volume_24h": 0,
                        "market_cap": 0,
                    }

        return results

    async def get_forex_rate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """Get exchange rate between two currencies."""
        cache_key = f"forex:{from_currency}:{to_currency}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return Decimal(cached)
        except Exception as e:
            print(f"Redis cache read error for forex: {e}")

        try:
            response = await self.http_client.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            )
            response.raise_for_status()
            data = response.json()

            rate = data.get("rates", {}).get(to_currency)
            if rate:
                try:
                    self.redis.setex(cache_key, self.CACHE_TTL_FOREX, str(rate))
                except Exception as e:
                    print(f"Redis cache write error for forex: {e}")
                return Decimal(str(rate))

        except Exception as e:
            print(f"Error fetching forex rate {from_currency}/{to_currency}: {e}")

        return None


    async def get_historical_crypto_price(
        self, symbol: str, date: datetime, currency: str = "eur"
    ) -> Optional[Decimal]:
        """Fetch historical cryptocurrency price from CoinGecko.

        Args:
            symbol: Crypto symbol (e.g., BTC, ETH)
            date: The date to get the price for
            currency: Target currency (default: eur)

        Returns:
            Price at the given date or None if not found
        """
        coin_id = self.SYMBOL_MAP.get(symbol.upper(), symbol.lower())

        # Format date as dd-mm-yyyy for CoinGecko
        date_str = date.strftime("%d-%m-%Y")

        # Check cache
        cache_key = f"price:historical:{coin_id}:{date_str}:{currency}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return Decimal(cached)
        except Exception as e:
            print(f"Redis cache read error for historical price: {e}")

        try:
            response = await self.http_client.get(
                f"{self.COINGECKO_BASE_URL}/coins/{coin_id}/history",
                params={
                    "date": date_str,
                    "localization": "false",
                },
            )
            response.raise_for_status()
            data = response.json()

            market_data = data.get("market_data", {})
            current_price = market_data.get("current_price", {})
            price = current_price.get(currency)

            if price:
                price_decimal = Decimal(str(price))
                # Cache for 24 hours (historical prices don't change)
                try:
                    self.redis.setex(cache_key, 86400, str(price_decimal))
                except Exception as e:
                    print(f"Redis cache write error for historical price: {e}")
                return price_decimal

        except Exception as e:
            print(f"Error fetching historical price for {symbol} on {date_str}: {e}")

        return None

    async def get_multiple_historical_prices(
        self,
        requests: list[tuple[str, datetime]],
        currency: str = "eur"
    ) -> dict[str, Decimal]:
        """Fetch multiple historical prices with rate limiting.

        Args:
            requests: List of (symbol, date) tuples
            currency: Target currency

        Returns:
            Dict mapping "symbol_date" to price
        """
        results = {}

        for symbol, date in requests:
            key = f"{symbol}_{date.strftime('%Y-%m-%d')}"
            price = await self.get_historical_crypto_price(symbol, date, currency)
            if price:
                results[key] = price
            # Small delay to avoid rate limiting (50 req/min = ~1.2s between requests)
            await asyncio.sleep(1.5)

        return results


# Singleton instance
price_service = PriceService()
