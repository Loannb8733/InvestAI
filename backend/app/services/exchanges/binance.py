"""Binance exchange service."""

import asyncio
import hashlib
import hmac
import ssl
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlencode

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeFiatOrder,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class BinanceService(BaseExchangeService):
    """Binance exchange integration."""

    BASE_URL = "https://api.binance.com"
    _server_time_offset: int = 0  # Offset between local time and Binance server time

    @property
    def exchange_name(self) -> str:
        return "Binance"

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context forcing TLS 1.2 for compatibility with Docker networking."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_default_certs()
        return context

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        """Create HTTP client with TLS 1.2 for Binance API."""
        return httpx.AsyncClient(
            verify=self._get_ssl_context(),
            timeout=timeout,
        )

    async def _sync_server_time(self) -> None:
        """Synchronize with Binance server time to avoid timestamp errors."""
        try:
            async with self._get_http_client(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/v3/time",
                )
                if response.status_code == 200:
                    server_time = response.json().get("serverTime", 0)
                    local_time = int(time.time() * 1000)
                    self._server_time_offset = server_time - local_time
                    print(f"Binance time sync: offset = {self._server_time_offset}ms")
        except Exception as e:
            print(f"Failed to sync Binance server time: {e}")
            self._server_time_offset = 0

    def _get_timestamp(self) -> int:
        """Get timestamp adjusted for Binance server time."""
        return int(time.time() * 1000) + self._server_time_offset

    def _sign_request(self, params: dict) -> dict:
        """Sign a request with HMAC SHA256."""
        params["timestamp"] = self._get_timestamp()
        params["recvWindow"] = 60000  # 60 seconds window for safety
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {"X-MBX-APIKEY": self.api_key}

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            # Sync server time first
            await self._sync_server_time()

            async with self._get_http_client(timeout=15.0) as client:
                params = self._sign_request({})
                response = await client.get(
                    f"{self.BASE_URL}/api/v3/account",
                    params=params,
                    headers=self._get_headers(),
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Binance test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Binance."""
        balances = []

        # Sync server time first
        await self._sync_server_time()

        async with self._get_http_client(timeout=30.0) as client:
            params = self._sign_request({})
            response = await client.get(
                f"{self.BASE_URL}/api/v3/account",
                params=params,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()

            for asset in data.get("balances", []):
                free = Decimal(asset["free"])
                locked = Decimal(asset["locked"])
                total = free + locked

                if total > 0:
                    balances.append(
                        ExchangeBalance(
                            symbol=asset["asset"],
                            free=free,
                            locked=locked,
                            total=total,
                        )
                    )

        return balances

    # Quote currencies to try for each base asset (prioritized by popularity)
    QUOTE_CURRENCIES = ["USDT", "EUR", "USDC", "BTC", "FDUSD"]

    # Fiat currencies (not tracked as assets)
    FIAT_CURRENCIES = ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD"]

    # Cache for valid trading pairs
    _valid_pairs: set = set()

    async def _get_valid_trading_pairs(self) -> set:
        """Fetch all valid trading pairs from Binance exchange info."""
        if self._valid_pairs:
            return self._valid_pairs

        try:
            async with self._get_http_client(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/v3/exchangeInfo",
                )
                if response.status_code == 200:
                    data = response.json()
                    self._valid_pairs = {
                        symbol["symbol"]
                        for symbol in data.get("symbols", [])
                        if symbol.get("status") == "TRADING"
                    }
                    print(f"Binance: {len(self._valid_pairs)} valid trading pairs cached")
        except Exception as e:
            print(f"Error fetching exchange info: {e}")

        return self._valid_pairs

    async def _fetch_trades_for_symbol(
        self,
        client: httpx.AsyncClient,
        trading_symbol: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        semaphore: asyncio.Semaphore,
    ) -> List[ExchangeTrade]:
        """Fetch trades for a single trading symbol with rate limiting."""
        trades = []

        async with semaphore:
            try:
                params = {"symbol": trading_symbol, "limit": min(limit, 1000)}

                if start_time:
                    params["startTime"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["endTime"] = int(end_time.timestamp() * 1000)

                params = self._sign_request(params)
                response = await client.get(
                    f"{self.BASE_URL}/api/v3/myTrades",
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code != 200:
                    return trades

                data = response.json()
                if data:
                    print(f"Binance: Found {len(data)} trades for {trading_symbol}")

                for trade in data:
                    side = "buy" if trade["isBuyer"] else "sell"
                    trades.append(
                        ExchangeTrade(
                            trade_id=str(trade["id"]),
                            symbol=trading_symbol,
                            side=side,
                            quantity=Decimal(trade["qty"]),
                            price=Decimal(trade["price"]),
                            fee=Decimal(trade["commission"]),
                            fee_currency=trade["commissionAsset"],
                            timestamp=datetime.fromtimestamp(trade["time"] / 1000),
                        )
                    )
            except Exception:
                pass

        return trades

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Binance using parallel requests."""
        # Sync server time first
        await self._sync_server_time()

        # Get valid trading pairs from Binance
        valid_pairs = await self._get_valid_trading_pairs()

        # Build list of trading pairs dynamically from user's balances
        symbols_to_fetch = set()

        if symbol:
            # Convert symbol to Binance pair format (e.g., BTC -> BTCUSDT, BTCEUR, etc.)
            for quote in self.QUOTE_CURRENCIES:
                pair = f"{symbol}{quote}"
                if pair in valid_pairs:
                    symbols_to_fetch.add(pair)
        else:
            # Get ALL assets from user's balances and build trading pairs
            try:
                balances = await self.get_balances()
                print(f"Binance: Found {len(balances)} assets with balance > 0")

                for balance in balances:
                    # Skip fiat currencies
                    if balance.symbol in self.FIAT_CURRENCIES:
                        continue

                    # Try quote currencies for each asset - only if pair exists
                    for quote in self.QUOTE_CURRENCIES:
                        if balance.symbol != quote:
                            pair = f"{balance.symbol}{quote}"
                            if pair in valid_pairs:
                                symbols_to_fetch.add(pair)

            except Exception as e:
                print(f"Error fetching balances for trade pairs: {e}")

        symbols_list = list(symbols_to_fetch)
        print(f"Binance: Fetching trades for {len(symbols_list)} valid trading pairs (parallel)...")

        # Use semaphore for rate limiting (10 concurrent requests)
        semaphore = asyncio.Semaphore(10)

        async with self._get_http_client() as client:
            # Create tasks for all symbols
            tasks = [
                self._fetch_trades_for_symbol(
                    client, trading_symbol, start_time, end_time, limit, semaphore
                )
                for trading_symbol in symbols_list
            ]

            # Execute all tasks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all trades from results
        all_trades = []
        for result in results:
            if isinstance(result, list):
                all_trades.extend(result)

        print(f"Binance: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Binance."""
        deposits = []

        # Sync server time first
        await self._sync_server_time()

        async with self._get_http_client() as client:
            params = {}
            if symbol:
                params["coin"] = symbol
            if start_time:
                params["startTime"] = int(start_time.timestamp() * 1000)

            params = self._sign_request(params)
            response = await client.get(
                f"{self.BASE_URL}/sapi/v1/capital/deposit/hisrec",
                params=params,
                headers=self._get_headers(),
                timeout=30.0,
            )

            if response.status_code != 200:
                return deposits

            data = response.json()

            for deposit in data[:limit]:
                status_map = {0: "pending", 1: "success", 6: "credited"}
                deposits.append(
                    ExchangeDeposit(
                        deposit_id=deposit.get("id", deposit.get("txId", "")),
                        symbol=deposit["coin"],
                        amount=Decimal(deposit["amount"]),
                        timestamp=datetime.fromtimestamp(deposit["insertTime"] / 1000),
                        status=status_map.get(deposit["status"], "unknown"),
                        tx_id=deposit.get("txId"),
                    )
                )

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Binance."""
        withdrawals = []

        # Sync server time first
        await self._sync_server_time()

        async with self._get_http_client() as client:
            params = {}
            if symbol:
                params["coin"] = symbol
            if start_time:
                params["startTime"] = int(start_time.timestamp() * 1000)

            params = self._sign_request(params)
            response = await client.get(
                f"{self.BASE_URL}/sapi/v1/capital/withdraw/history",
                params=params,
                headers=self._get_headers(),
                timeout=30.0,
            )

            if response.status_code != 200:
                return withdrawals

            data = response.json()

            for withdrawal in data[:limit]:
                status_map = {
                    0: "email_sent",
                    1: "cancelled",
                    2: "awaiting_approval",
                    3: "rejected",
                    4: "processing",
                    5: "failure",
                    6: "completed",
                }
                withdrawals.append(
                    ExchangeWithdrawal(
                        withdrawal_id=withdrawal["id"],
                        symbol=withdrawal["coin"],
                        amount=Decimal(withdrawal["amount"]),
                        fee=Decimal(withdrawal.get("transactionFee", 0)),
                        timestamp=datetime.fromisoformat(
                            withdrawal["applyTime"].replace("Z", "+00:00")
                        ),
                        status=status_map.get(withdrawal["status"], "unknown"),
                        tx_id=withdrawal.get("txId"),
                        address=withdrawal.get("address"),
                    )
                )

        return withdrawals

    async def get_fiat_orders(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeFiatOrder]:
        """Get fiat buy/sell order history from Binance."""
        orders = []

        # Sync server time first
        await self._sync_server_time()

        # Default: query from 2017 (Binance launch) to now
        if not start_time:
            start_time = datetime(2017, 7, 1)  # Binance launched July 2017
        if not end_time:
            end_time = datetime.now()

        async with self._get_http_client() as client:
            # Get both buy (0) and sell (1) orders
            for transaction_type in [0, 1]:
                # Query in 90-day chunks (API limitation)
                chunk_end = end_time
                total_orders_for_type = 0

                while chunk_end > start_time:
                    chunk_start = max(chunk_end - timedelta(days=90), start_time)

                    # Query multiple pages for each chunk
                    page = 1
                    max_pages = 20  # Safety limit

                    while page <= max_pages:
                        try:
                            params = {
                                "transactionType": transaction_type,
                                "beginTime": int(chunk_start.timestamp() * 1000),
                                "endTime": int(chunk_end.timestamp() * 1000),
                                "rows": 500,
                                "page": page,
                            }

                            print(f"Fiat orders API: type={transaction_type}, page={page}, {chunk_start.date()} to {chunk_end.date()}")

                            params = self._sign_request(params)
                            response = await client.get(
                                f"{self.BASE_URL}/sapi/v1/fiat/payments",
                                params=params,
                                headers=self._get_headers(),
                                timeout=30.0,
                            )

                            if response.status_code != 200:
                                print(f"Fiat orders API error: {response.status_code} - {response.text[:200]}")
                                break

                            data = response.json()
                            page_data = data.get("data", [])

                            if not page_data:
                                break

                            print(f"Fiat orders: found {len(page_data)} orders (type={transaction_type}, page={page})")
                            if page == 1 and page_data:
                                print(f"Sample: {page_data[0]}")

                            for order in page_data:
                                # Only include completed orders
                                if order.get("status") != "Completed":
                                    continue

                                side = "buy" if transaction_type == 0 else "sell"
                                crypto_amount = Decimal(str(order.get("obtainAmount", 0)))
                                fiat_amount = Decimal(str(order.get("sourceAmount", 0)))

                                # For sell orders, amounts are reversed
                                if side == "sell":
                                    crypto_amount = Decimal(str(order.get("sourceAmount", 0)))
                                    fiat_amount = Decimal(str(order.get("obtainAmount", 0)))

                                # Calculate price per crypto
                                price = fiat_amount / crypto_amount if crypto_amount > 0 else Decimal("0")

                                orders.append(
                                    ExchangeFiatOrder(
                                        order_id=order.get("orderNo", str(order.get("createTime", ""))),
                                        crypto_symbol=order.get("cryptoCurrency", ""),
                                        fiat_currency=order.get("fiatCurrency", "EUR"),
                                        side=side,
                                        crypto_amount=crypto_amount,
                                        fiat_amount=fiat_amount,
                                        price=price,
                                        fee=Decimal(str(order.get("totalFee", 0))),
                                        status=order.get("status", "unknown"),
                                        timestamp=datetime.fromtimestamp(order.get("createTime", 0) / 1000),
                                    )
                                )
                                total_orders_for_type += 1

                            # If we got less than 500, we've reached the end for this chunk
                            if len(page_data) < 500:
                                break

                            page += 1

                        except Exception as e:
                            print(f"Error fetching fiat orders: {e}")
                            break

                    # Move to previous chunk
                    chunk_end = chunk_start - timedelta(seconds=1)

                print(f"Total fiat orders for type {transaction_type}: {total_orders_for_type}")

        print(f"Total fiat orders found: {len(orders)}")
        return sorted(orders, key=lambda x: x.timestamp, reverse=True)

    async def get_convert_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[ExchangeFiatOrder]:
        """Get convert trade history from Binance (EUR -> BTC conversions)."""
        orders = []

        # Sync server time first (only if not already synced recently)
        await self._sync_server_time()

        async with self._get_http_client() as client:
            try:
                params = {
                    "limit": min(limit, 1000),
                }

                # Add time range if specified
                if start_time:
                    params["startTime"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["endTime"] = int(end_time.timestamp() * 1000)

                params = self._sign_request(params)
                response = await client.get(
                    f"{self.BASE_URL}/sapi/v1/convert/tradeFlow",
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code != 200:
                    print(f"Convert history API error: {response.status_code} - {response.text[:200]}")
                    return orders

                data = response.json()
                convert_list = data.get("list", [])

                if convert_list:
                    print(f"Convert history: {len(convert_list)} conversions found")

                for conv in convert_list:
                    # Determine which is crypto and which is fiat
                    from_asset = conv.get("fromAsset", "")
                    to_asset = conv.get("toAsset", "")
                    from_amount = Decimal(str(conv.get("fromAmount", 0)))
                    to_amount = Decimal(str(conv.get("toAmount", 0)))

                    fiat_currencies = ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL"]
                    stablecoins = ["USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"]

                    # If from is fiat/stablecoin and to is crypto -> BUY
                    if (from_asset in fiat_currencies or from_asset in stablecoins) and to_asset not in fiat_currencies:
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=str(conv.get("quoteId", conv.get("orderId", ""))),
                                crypto_symbol=to_asset,
                                fiat_currency=from_asset,
                                side="buy",
                                crypto_amount=to_amount,
                                fiat_amount=from_amount,
                                price=from_amount / to_amount if to_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000),
                            )
                        )
                    # If from is crypto and to is fiat/stablecoin -> SELL
                    elif from_asset not in fiat_currencies and (to_asset in fiat_currencies or to_asset in stablecoins):
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=str(conv.get("quoteId", conv.get("orderId", ""))),
                                crypto_symbol=from_asset,
                                fiat_currency=to_asset,
                                side="sell",
                                crypto_amount=from_amount,
                                fiat_amount=to_amount,
                                price=to_amount / from_amount if from_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000),
                            )
                        )
                    # Crypto to crypto conversion (e.g., BTC -> ETH)
                    elif from_asset not in fiat_currencies and from_asset not in stablecoins:
                        # Treat as sell of from_asset
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=f"sell_{conv.get('quoteId', conv.get('orderId', ''))}",
                                crypto_symbol=from_asset,
                                fiat_currency=to_asset,
                                side="sell",
                                crypto_amount=from_amount,
                                fiat_amount=to_amount,
                                price=to_amount / from_amount if from_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000),
                            )
                        )
                        # And buy of to_asset
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=f"buy_{conv.get('quoteId', conv.get('orderId', ''))}",
                                crypto_symbol=to_asset,
                                fiat_currency=from_asset,
                                side="buy",
                                crypto_amount=to_amount,
                                fiat_amount=from_amount,
                                price=from_amount / to_amount if to_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000),
                            )
                        )

            except Exception as e:
                print(f"Error fetching convert history: {e}")

        return orders

    async def get_crypto_conversions(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get crypto-to-crypto conversions from Binance Convert feature.

        Filters convert history to only return true crypto-to-crypto swaps,
        excluding fiat and stablecoin conversions.
        """
        conversions = []

        # Define what we consider fiat/stablecoins (not true crypto)
        fiat_currencies = ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD"]
        stablecoins = ["USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD"]

        # Sync server time
        await self._sync_server_time()

        # Query in 30-day chunks from start to end
        if not start_time:
            start_time = datetime(2017, 7, 1)
        if not end_time:
            end_time = datetime.now()

        chunk_end = end_time

        async with self._get_http_client() as client:
            while chunk_end > start_time:
                chunk_start = max(chunk_end - timedelta(days=30), start_time)

                try:
                    params = {
                        "limit": min(limit, 1000),
                        "startTime": int(chunk_start.timestamp() * 1000),
                        "endTime": int(chunk_end.timestamp() * 1000),
                    }

                    params = self._sign_request(params)
                    response = await client.get(
                        f"{self.BASE_URL}/sapi/v1/convert/tradeFlow",
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        chunk_end = chunk_start - timedelta(seconds=1)
                        continue

                    data = response.json()
                    convert_list = data.get("list", [])

                    for conv in convert_list:
                        from_asset = conv.get("fromAsset", "")
                        to_asset = conv.get("toAsset", "")
                        from_amount = Decimal(str(conv.get("fromAmount", 0)))
                        to_amount = Decimal(str(conv.get("toAmount", 0)))
                        order_id = str(conv.get("quoteId", conv.get("orderId", "")))
                        timestamp = datetime.fromtimestamp(conv.get("createTime", 0) / 1000)

                        # Skip if from is fiat (can't convert from fiat here)
                        if from_asset in fiat_currencies:
                            continue

                        # Calculate conversion rate
                        rate = to_amount / from_amount if from_amount > 0 else Decimal("0")

                        # Handle differently based on whether stablecoins are involved
                        if to_asset in fiat_currencies:
                            # Crypto -> Fiat: this is a SELL, skip (handled by fiat orders)
                            continue
                        elif to_asset in stablecoins:
                            # Crypto -> Stablecoin: SELL of crypto (user converts crypto to stable)
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,  # Rate in stablecoin per crypto
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            # Also track the stablecoin received
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            print(f"Binance: Found conversion {from_asset} -> {to_asset} (to stablecoin)")
                        elif from_asset in stablecoins:
                            # Stablecoin -> Crypto: BUY of crypto (user buys crypto with stable)
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            print(f"Binance: Found conversion {from_asset} -> {to_asset} (from stablecoin)")
                        else:
                            # True crypto-to-crypto conversion
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            print(f"Binance: Found conversion {from_asset} -> {to_asset}")

                except Exception as e:
                    print(f"Error fetching Binance conversions: {e}")

                chunk_end = chunk_start - timedelta(seconds=1)

        print(f"Binance: Total crypto conversions found: {len(conversions) // 2}")
        return sorted(conversions, key=lambda x: x.timestamp, reverse=True)

    async def get_auto_invest_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeFiatOrder]:
        """Get Auto-Invest (DCA) history from Binance."""
        orders = []

        async with self._get_http_client() as client:
            try:
                params = {
                    "size": min(limit, 100),
                }

                if start_time:
                    params["startTime"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["endTime"] = int(end_time.timestamp() * 1000)

                params = self._sign_request(params)
                response = await client.get(
                    f"{self.BASE_URL}/sapi/v1/lending/auto-invest/history/list",
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code != 200:
                    # API might not be available for this user
                    return orders

                data = response.json()
                invest_list = data.get("list", [])

                if invest_list:
                    print(f"Auto-invest history: {len(invest_list)} orders found")

                for invest in invest_list:
                    if invest.get("status") != "SUCCESS":
                        continue

                    target_asset = invest.get("targetAsset", "")
                    source_asset = invest.get("sourceAsset", "EUR")
                    executed_amount = Decimal(str(invest.get("executedAmount", 0)))
                    source_amount = Decimal(str(invest.get("sourceAssetAmount", 0)))

                    if executed_amount > 0:
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=f"autoinvest_{invest.get('id', invest.get('transactionTime', ''))}",
                                crypto_symbol=target_asset,
                                fiat_currency=source_asset,
                                side="buy",
                                crypto_amount=executed_amount,
                                fiat_amount=source_amount,
                                price=source_amount / executed_amount if executed_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(invest.get("transactionTime", 0) / 1000),
                            )
                        )

            except Exception as e:
                print(f"Error fetching auto-invest history: {e}")

        return orders

    async def get_simple_earn_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeFiatOrder]:
        """Get Simple Earn (flexible/locked savings) purchase history."""
        orders = []

        async with self._get_http_client() as client:
            try:
                params = {
                    "size": min(limit, 100),
                    "current": 1,
                }

                if start_time:
                    params["startTime"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["endTime"] = int(end_time.timestamp() * 1000)

                params = self._sign_request(params)
                response = await client.get(
                    f"{self.BASE_URL}/sapi/v1/simple-earn/flexible/history/subscriptionRecord",
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code != 200:
                    return orders

                data = response.json()
                rows = data.get("rows", [])

                if rows:
                    print(f"Simple earn subscriptions: {len(rows)} found")

                for row in rows:
                    if row.get("status") != "SUCCESS":
                        continue

                    orders.append(
                        ExchangeFiatOrder(
                            order_id=f"earn_{row.get('id', '')}",
                            crypto_symbol=row.get("asset", ""),
                            fiat_currency="EUR",
                            side="buy",
                            crypto_amount=Decimal(str(row.get("amount", 0))),
                            fiat_amount=Decimal("0"),  # Already owned, just moved to earn
                            price=Decimal("0"),
                            fee=Decimal("0"),
                            status="Completed",
                            timestamp=datetime.fromtimestamp(row.get("time", 0) / 1000),
                        )
                    )

            except Exception as e:
                print(f"Error fetching simple earn history: {e}")

        return orders
