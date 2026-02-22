"""Coinbase Advanced Trade exchange service."""

import hashlib
import hmac
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class CoinbaseService(BaseExchangeService):
    """Coinbase Advanced Trade exchange integration."""

    BASE_URL = "https://api.coinbase.com"

    @property
    def exchange_name(self) -> str:
        return "Coinbase"

    def _get_timestamp(self) -> str:
        """Get current UNIX timestamp as string."""
        return str(int(time.time()))

    def _sign_request(self, method: str, request_path: str, body: str = "") -> dict:
        """Sign a request with HMAC SHA256.

        Coinbase signature: HMAC-SHA256 of (timestamp + method + requestPath + body).
        """
        timestamp = self._get_timestamp()
        message = timestamp + method.upper() + request_path + body

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            request_path = "/api/v3/brokerage/accounts?limit=1"
            headers = self._sign_request("GET", request_path)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Coinbase test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Coinbase.

        Paginates through all accounts using the cursor-based pagination.
        """
        balances = []

        try:
            cursor = None

            async with httpx.AsyncClient() as client:
                while True:
                    request_path = "/api/v3/brokerage/accounts?limit=250"
                    if cursor:
                        request_path += f"&cursor={cursor}"

                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    for account in data.get("accounts", []):
                        available = Decimal(account.get("available_balance", {}).get("value", "0"))
                        hold = Decimal(account.get("hold", {}).get("value", "0"))
                        total = available + hold

                        if total > 0:
                            balances.append(
                                ExchangeBalance(
                                    symbol=account.get("currency", ""),
                                    free=available,
                                    locked=hold,
                                    total=total,
                                )
                            )

                    # Check for next page
                    cursor = data.get("cursor")
                    if not cursor or not data.get("has_next", False):
                        break

        except Exception as e:
            logger.error(f"Coinbase get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history (fills) from Coinbase.

        Uses the historical fills endpoint with cursor-based pagination.
        """
        trades = []

        try:
            cursor = None
            fetched = 0

            async with httpx.AsyncClient() as client:
                while fetched < limit:
                    page_size = min(limit - fetched, 100)
                    request_path = f"/api/v3/brokerage/orders/historical/fills?limit={page_size}"

                    if symbol:
                        # Coinbase uses product_id format like "BTC-USD"
                        request_path += f"&product_id={symbol}"
                    if start_time:
                        request_path += f"&start_sequence_timestamp={start_time.isoformat()}Z"
                    if end_time:
                        request_path += f"&end_sequence_timestamp={end_time.isoformat()}Z"
                    if cursor:
                        request_path += f"&cursor={cursor}"

                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"Coinbase get_trades error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()
                    fills = data.get("fills", [])

                    if not fills:
                        break

                    for fill in fills:
                        # product_id is like "BTC-USD", "ETH-EUR"
                        product_id = fill.get("product_id", "")

                        trades.append(
                            ExchangeTrade(
                                trade_id=fill.get("trade_id", fill.get("entry_id", "")),
                                symbol=product_id,
                                side=fill.get("side", "").lower(),
                                quantity=Decimal(fill.get("size", "0")),
                                price=Decimal(fill.get("price", "0")),
                                fee=Decimal(fill.get("commission", "0")),
                                fee_currency=product_id.split("-")[-1] if "-" in product_id else "USD",
                                timestamp=datetime.fromisoformat(fill.get("trade_time", "").replace("Z", "+00:00")),
                            )
                        )

                    fetched += len(fills)

                    # Check for next page
                    cursor = data.get("cursor")
                    if not cursor:
                        break

        except Exception as e:
            logger.error(f"Coinbase get_trades error: {e}")

        logger.info(f"Coinbase: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Coinbase.

        Uses the transaction_summary or account transactions to retrieve deposits.
        Coinbase Advanced Trade API uses account-level transaction listing.
        """
        deposits = []

        try:
            # First, get all accounts to find account UUIDs
            accounts = await self._get_account_ids(symbol)

            async with httpx.AsyncClient() as client:
                for account_id, currency in accounts:
                    if len(deposits) >= limit:
                        break

                    request_path = f"/api/v3/brokerage/accounts/{account_id}/transactions?limit=100&type=deposit"
                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        # Fallback: try the v2 transactions endpoint
                        request_path_v2 = f"/v2/accounts/{account_id}/deposits"
                        headers_v2 = self._sign_request("GET", request_path_v2)

                        response = await client.get(
                            f"{self.BASE_URL}{request_path_v2}",
                            headers=headers_v2,
                            timeout=30.0,
                        )

                        if response.status_code != 200:
                            continue

                    data = response.json()
                    transactions = data.get("transactions", data.get("data", []))

                    for tx in transactions:
                        if len(deposits) >= limit:
                            break

                        # Filter by start_time if provided
                        tx_time = tx.get("created_at", tx.get("payout_at", ""))
                        if tx_time:
                            tx_datetime = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
                            if start_time and tx_datetime < start_time:
                                continue
                        else:
                            tx_datetime = datetime.now()

                        amount_data = tx.get("amount", {})
                        amount = Decimal(amount_data.get("value", amount_data.get("amount", "0")))

                        deposits.append(
                            ExchangeDeposit(
                                deposit_id=tx.get("id", ""),
                                symbol=amount_data.get("currency", currency),
                                amount=abs(amount),
                                timestamp=tx_datetime,
                                status=tx.get("status", "completed"),
                                tx_id=tx.get("network", {}).get("hash"),
                            )
                        )

        except Exception as e:
            logger.error(f"Coinbase get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Coinbase.

        Uses account-level transaction listing to retrieve withdrawals.
        """
        withdrawals = []

        try:
            # First, get all accounts to find account UUIDs
            accounts = await self._get_account_ids(symbol)

            async with httpx.AsyncClient() as client:
                for account_id, currency in accounts:
                    if len(withdrawals) >= limit:
                        break

                    request_path = f"/api/v3/brokerage/accounts/{account_id}/transactions?limit=100&type=withdrawal"
                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        # Fallback: try the v2 transactions endpoint
                        request_path_v2 = f"/v2/accounts/{account_id}/withdrawals"
                        headers_v2 = self._sign_request("GET", request_path_v2)

                        response = await client.get(
                            f"{self.BASE_URL}{request_path_v2}",
                            headers=headers_v2,
                            timeout=30.0,
                        )

                        if response.status_code != 200:
                            continue

                    data = response.json()
                    transactions = data.get("transactions", data.get("data", []))

                    for tx in transactions:
                        if len(withdrawals) >= limit:
                            break

                        # Filter by start_time if provided
                        tx_time = tx.get("created_at", tx.get("payout_at", ""))
                        if tx_time:
                            tx_datetime = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
                            if start_time and tx_datetime < start_time:
                                continue
                        else:
                            tx_datetime = datetime.now()

                        amount_data = tx.get("amount", {})
                        amount = Decimal(amount_data.get("value", amount_data.get("amount", "0")))
                        fee_data = tx.get("fee", {})
                        fee = Decimal(fee_data.get("value", fee_data.get("amount", "0")))

                        network_data = tx.get("network", {})

                        withdrawals.append(
                            ExchangeWithdrawal(
                                withdrawal_id=tx.get("id", ""),
                                symbol=amount_data.get("currency", currency),
                                amount=abs(amount),
                                fee=abs(fee),
                                timestamp=tx_datetime,
                                status=tx.get("status", "completed"),
                                tx_id=network_data.get("hash"),
                                address=network_data.get("to_address_info", {}).get("address"),
                            )
                        )

        except Exception as e:
            logger.error(f"Coinbase get_withdrawals error: {e}")

        return withdrawals

    async def _get_account_ids(self, symbol: Optional[str] = None) -> List[tuple]:
        """Get account UUIDs from Coinbase.

        Returns list of (account_id, currency) tuples.
        If symbol is provided, only returns matching accounts.
        """
        accounts = []

        try:
            cursor = None

            async with httpx.AsyncClient() as client:
                while True:
                    request_path = "/api/v3/brokerage/accounts?limit=250"
                    if cursor:
                        request_path += f"&cursor={cursor}"

                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        break

                    data = response.json()

                    for account in data.get("accounts", []):
                        currency = account.get("currency", "")
                        if symbol and currency != symbol:
                            continue
                        accounts.append((account.get("uuid", ""), currency))

                    cursor = data.get("cursor")
                    if not cursor or not data.get("has_next", False):
                        break

        except Exception as e:
            logger.error(f"Coinbase _get_account_ids error: {e}")

        return accounts

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize Coinbase symbol to standard format.

        Coinbase uses standard symbols (BTC, ETH, SOL) so minimal
        normalization is needed. Product IDs use dash format (BTC-USD).
        """
        # Handle product_id format (e.g., "BTC-USD" -> "BTC")
        if "-" in symbol:
            return symbol.split("-")[0]
        return symbol
