"""Crypto.com exchange service."""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class CryptoComService(BaseExchangeService):
    """Crypto.com exchange integration."""

    BASE_URL = "https://api.crypto.com/v2"

    @property
    def exchange_name(self) -> str:
        return "Crypto.com"

    def _sign_request(self, method: str, request_id: str, params: dict) -> str:
        """Sign a request with Crypto.com's signature method."""
        param_string = ""
        if params:
            # Sort params alphabetically
            sorted_params = sorted(params.items())
            param_string = "".join(f"{k}{v}" for k, v in sorted_params)

        nonce = str(int(time.time() * 1000))
        sig_payload = f"{method}{request_id}{self.api_key}{param_string}{nonce}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sig_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    async def _make_request(
        self, method: str, params: Optional[dict] = None
    ) -> dict:
        """Make an authenticated request to Crypto.com API."""
        request_id = str(int(time.time() * 1000))
        nonce = str(int(time.time() * 1000))

        if params is None:
            params = {}

        signature = self._sign_request(method, request_id, params)

        payload = {
            "id": request_id,
            "method": method,
            "api_key": self.api_key,
            "params": params,
            "sig": signature,
            "nonce": nonce,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{method}",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            result = await self._make_request("private/get-account-summary")
            return result.get("code") == 0
        except Exception:
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Crypto.com."""
        balances = []

        try:
            result = await self._make_request("private/get-account-summary")

            if result.get("code") != 0:
                return balances

            accounts = result.get("result", {}).get("accounts", [])

            for account in accounts:
                balance = Decimal(str(account.get("balance", 0)))
                available = Decimal(str(account.get("available", 0)))

                if balance > 0:
                    balances.append(
                        ExchangeBalance(
                            symbol=account["currency"],
                            free=available,
                            locked=balance - available,
                            total=balance,
                        )
                    )
        except Exception:
            pass

        return balances

    # Quote currencies to try for each base asset (prioritized)
    QUOTE_CURRENCIES = ["USDT", "USD", "EUR", "BTC", "CRO"]

    # Fiat currencies (not tracked as assets)
    FIAT_CURRENCIES = ["EUR", "USD", "GBP", "AUD", "CAD", "SGD"]

    async def _fetch_trades_for_instrument(
        self,
        instrument: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        semaphore: asyncio.Semaphore,
    ) -> List[ExchangeTrade]:
        """Fetch trades for a single instrument with rate limiting."""
        trades = []

        async with semaphore:
            try:
                params = {"page_size": min(limit, 200), "instrument_name": instrument}

                if start_time:
                    params["start_ts"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["end_ts"] = int(end_time.timestamp() * 1000)

                result = await self._make_request("private/get-trades", params)

                if result.get("code") != 0:
                    return trades

                trade_list = result.get("result", {}).get("trade_list", [])

                if trade_list:
                    print(f"Crypto.com: Found {len(trade_list)} trades for {instrument}")

                for trade in trade_list:
                    instrument_name = trade.get("instrument_name", "")

                    trades.append(
                        ExchangeTrade(
                            trade_id=str(trade["trade_id"]),
                            symbol=instrument_name,
                            side=trade["side"].lower(),
                            quantity=Decimal(str(trade["traded_quantity"])),
                            price=Decimal(str(trade["traded_price"])),
                            fee=Decimal(str(trade.get("fee", 0))),
                            fee_currency=trade.get("fee_currency", "USDT"),
                            timestamp=datetime.fromtimestamp(
                                trade["create_time"] / 1000
                            ),
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
        """Get trade history from Crypto.com using parallel requests."""
        # Build list of instruments to fetch dynamically from user's balances
        instruments_to_fetch = set()

        if symbol:
            # Fetch specific symbol with multiple quote currencies
            for quote in self.QUOTE_CURRENCIES:
                if symbol != quote:
                    instruments_to_fetch.add(f"{symbol}_{quote}")
        else:
            # Get ALL assets from user's balances and build instrument names
            try:
                balances = await self.get_balances()
                print(f"Crypto.com: Found {len(balances)} assets with balance > 0")

                for balance in balances:
                    # Skip fiat currencies
                    if balance.symbol in self.FIAT_CURRENCIES:
                        continue

                    # Try quote currencies for each asset
                    for quote in self.QUOTE_CURRENCIES:
                        if balance.symbol != quote:
                            instruments_to_fetch.add(f"{balance.symbol}_{quote}")

            except Exception as e:
                print(f"Error fetching balances for trade instruments: {e}")

        instruments_list = list(instruments_to_fetch)
        print(f"Crypto.com: Fetching trades for {len(instruments_list)} instruments (parallel)...")

        # Use semaphore for rate limiting (5 concurrent requests)
        semaphore = asyncio.Semaphore(5)

        # Create tasks for all instruments
        tasks = [
            self._fetch_trades_for_instrument(
                instrument, start_time, end_time, limit, semaphore
            )
            for instrument in instruments_list
        ]

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all trades from results
        all_trades = []
        for result in results:
            if isinstance(result, list):
                all_trades.extend(result)

        print(f"Crypto.com: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Crypto.com."""
        deposits = []

        try:
            params = {"page_size": min(limit, 200)}

            if symbol:
                params["currency"] = symbol
            if start_time:
                params["start_ts"] = int(start_time.timestamp() * 1000)

            result = await self._make_request("private/get-deposit-history", params)

            if result.get("code") != 0:
                return deposits

            deposit_list = result.get("result", {}).get("deposit_list", [])

            for deposit in deposit_list:
                status_map = {
                    0: "pending",
                    1: "processing",
                    2: "completed",
                    3: "failed",
                }
                deposits.append(
                    ExchangeDeposit(
                        deposit_id=str(deposit.get("id", "")),
                        symbol=deposit["currency"],
                        amount=Decimal(str(deposit["amount"])),
                        timestamp=datetime.fromtimestamp(
                            deposit["create_time"] / 1000
                        ),
                        status=status_map.get(deposit.get("status", 0), "unknown"),
                        tx_id=deposit.get("txid"),
                    )
                )
        except Exception:
            pass

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Crypto.com."""
        withdrawals = []

        try:
            params = {"page_size": min(limit, 200)}

            if symbol:
                params["currency"] = symbol
            if start_time:
                params["start_ts"] = int(start_time.timestamp() * 1000)

            result = await self._make_request(
                "private/get-withdrawal-history", params
            )

            if result.get("code") != 0:
                return withdrawals

            withdrawal_list = result.get("result", {}).get("withdrawal_list", [])

            for withdrawal in withdrawal_list:
                status_map = {
                    0: "pending",
                    1: "processing",
                    2: "completed",
                    3: "cancelled",
                    4: "failed",
                }
                withdrawals.append(
                    ExchangeWithdrawal(
                        withdrawal_id=str(withdrawal.get("id", "")),
                        symbol=withdrawal["currency"],
                        amount=Decimal(str(withdrawal["amount"])),
                        fee=Decimal(str(withdrawal.get("fee", 0))),
                        timestamp=datetime.fromtimestamp(
                            withdrawal["create_time"] / 1000
                        ),
                        status=status_map.get(
                            withdrawal.get("status", 0), "unknown"
                        ),
                        tx_id=withdrawal.get("txid"),
                        address=withdrawal.get("address"),
                    )
                )
        except Exception:
            pass

        return withdrawals

    async def get_crypto_conversions(self, limit: int = 500) -> List[ExchangeTrade]:
        """
        Get crypto-to-crypto conversions from Crypto.com.

        Crypto.com tracks conversions as regular trades with crypto/crypto pairs.
        This method fetches trades where both base and quote are crypto (not fiat).
        """
        conversions = []

        try:
            # Get all assets from balances to build crypto-to-crypto pairs
            balances = await self.get_balances()
            crypto_assets = [
                b.symbol for b in balances
                if b.symbol not in self.FIAT_CURRENCIES
            ]

            print(f"Crypto.com: Checking {len(crypto_assets)} crypto assets for conversions...")

            # Build crypto-to-crypto pairs (e.g., BTC_CRO, ETH_BTC)
            crypto_pairs = set()
            for base in crypto_assets:
                for quote in crypto_assets:
                    if base != quote:
                        # Crypto.com uses underscores: BTC_CRO
                        crypto_pairs.add(f"{base}_{quote}")

            # Also check common conversion pairs
            common_crypto = ["BTC", "ETH", "CRO", "USDT", "USDC"]
            for base in common_crypto:
                for quote in common_crypto:
                    if base != quote and quote not in self.FIAT_CURRENCIES:
                        crypto_pairs.add(f"{base}_{quote}")

            pairs_list = list(crypto_pairs)
            print(f"Crypto.com: Checking {len(pairs_list)} crypto-to-crypto pairs...")

            # Use semaphore for rate limiting
            semaphore = asyncio.Semaphore(5)

            # Create tasks for all pairs
            tasks = [
                self._fetch_trades_for_instrument(
                    pair, None, None, limit, semaphore
                )
                for pair in pairs_list
            ]

            # Execute all tasks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect conversions from results
            for result in results:
                if isinstance(result, list):
                    for trade in result:
                        # Parse instrument name to get base and quote
                        parts = trade.symbol.split("_")
                        if len(parts) == 2:
                            quote = parts[1]
                            # Only include if quote is also crypto (not fiat)
                            if quote not in self.FIAT_CURRENCIES:
                                # Create new trade with convert_ prefix for identification
                                conversion_trade = ExchangeTrade(
                                    trade_id=f"convert_{trade.trade_id}",
                                    symbol=trade.symbol,
                                    side=trade.side,
                                    quantity=trade.quantity,
                                    price=trade.price,
                                    fee=trade.fee,
                                    fee_currency=trade.fee_currency,
                                    timestamp=trade.timestamp,
                                )
                                conversions.append(conversion_trade)

            print(f"Crypto.com: Found {len(conversions)} crypto-to-crypto conversions")

        except Exception as e:
            print(f"Error fetching Crypto.com conversions: {e}")

        return sorted(conversions, key=lambda x: x.timestamp, reverse=True)
