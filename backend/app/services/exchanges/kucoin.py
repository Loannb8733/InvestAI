"""KuCoin exchange service."""

import base64
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


class KuCoinService(BaseExchangeService):
    """KuCoin exchange integration (API v2)."""

    BASE_URL = "https://api.kucoin.com"

    @property
    def exchange_name(self) -> str:
        return "KuCoin"

    def _get_timestamp(self) -> str:
        """Get current UNIX timestamp in milliseconds as string."""
        return str(int(time.time() * 1000))

    def _sign_request(self, method: str, endpoint: str, body: str = "") -> dict:
        """Sign a request with HMAC SHA256 base64 encoding.

        KuCoin v2 signature: base64(HMAC-SHA256(timestamp + method + endpoint + body)).
        The passphrase is also HMAC-encrypted with the secret key for API v2.
        """
        timestamp = self._get_timestamp()
        message = timestamp + method.upper() + endpoint + body

        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        # KuCoin API v2: passphrase must also be HMAC-encrypted
        passphrase = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                (self.passphrase or "").encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            endpoint = "/api/v1/accounts"
            headers = self._sign_request("GET", endpoint)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=15.0,
                )
                data = response.json()
                return data.get("code") == "200000"
        except Exception as e:
            logger.error(f"KuCoin test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from KuCoin.

        Filters to 'trade' account type and returns only non-zero balances.
        """
        balances = []

        try:
            endpoint = "/api/v1/accounts?type=trade"
            headers = self._sign_request("GET", endpoint)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "200000":
                    logger.error(f"KuCoin get_balances error: {data.get('msg', 'Unknown error')}")
                    return balances

                for account in data.get("data", []):
                    available = Decimal(account.get("available", "0"))
                    holds = Decimal(account.get("holds", "0"))
                    total = available + holds

                    if total > 0:
                        balances.append(
                            ExchangeBalance(
                                symbol=account.get("currency", ""),
                                free=available,
                                locked=holds,
                                total=total,
                            )
                        )

        except Exception as e:
            logger.error(f"KuCoin get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history (fills) from KuCoin.

        Uses page-based pagination (currentPage, pageSize).
        """
        trades = []

        try:
            current_page = 1
            page_size = min(limit, 500)

            async with httpx.AsyncClient() as client:
                while len(trades) < limit:
                    endpoint = f"/api/v1/fills?currentPage={current_page}&pageSize={page_size}"

                    if symbol:
                        # KuCoin uses symbol format like "BTC-USDT"
                        endpoint += f"&symbol={symbol}"
                    if start_time:
                        endpoint += f"&startAt={int(start_time.timestamp() * 1000)}"
                    if end_time:
                        endpoint += f"&endAt={int(end_time.timestamp() * 1000)}"

                    headers = self._sign_request("GET", endpoint)

                    response = await client.get(
                        f"{self.BASE_URL}{endpoint}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"KuCoin get_trades error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()

                    if data.get("code") != "200000":
                        logger.error(f"KuCoin get_trades API error: {data.get('msg', 'Unknown error')}")
                        break

                    items = data.get("data", {}).get("items", [])

                    if not items:
                        break

                    for fill in items:
                        if len(trades) >= limit:
                            break

                        # symbol is like "BTC-USDT"
                        trade_symbol = fill.get("symbol", "")
                        fee_currency = fill.get("feeCurrency", "")

                        trades.append(
                            ExchangeTrade(
                                trade_id=fill.get("tradeId", ""),
                                symbol=trade_symbol,
                                side=fill.get("side", "").lower(),
                                quantity=Decimal(fill.get("size", "0")),
                                price=Decimal(fill.get("price", "0")),
                                fee=Decimal(fill.get("fee", "0")),
                                fee_currency=fee_currency,
                                timestamp=datetime.fromtimestamp(int(fill.get("createdAt", 0)) / 1000),
                            )
                        )

                    # Check if there are more pages
                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:
            logger.error(f"KuCoin get_trades error: {e}")

        logger.info(f"KuCoin: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from KuCoin."""
        deposits = []

        try:
            current_page = 1
            page_size = min(limit, 100)

            async with httpx.AsyncClient() as client:
                while len(deposits) < limit:
                    endpoint = f"/api/v1/deposits?currentPage={current_page}&pageSize={page_size}"

                    if symbol:
                        endpoint += f"&currency={symbol}"
                    if start_time:
                        endpoint += f"&startAt={int(start_time.timestamp() * 1000)}"

                    headers = self._sign_request("GET", endpoint)

                    response = await client.get(
                        f"{self.BASE_URL}{endpoint}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"KuCoin get_deposits error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()

                    if data.get("code") != "200000":
                        logger.error(f"KuCoin get_deposits API error: {data.get('msg', 'Unknown error')}")
                        break

                    items = data.get("data", {}).get("items", [])

                    if not items:
                        break

                    for deposit in items:
                        if len(deposits) >= limit:
                            break

                        status_map = {
                            "PROCESSING": "processing",
                            "SUCCESS": "success",
                            "FAILURE": "failure",
                        }

                        deposits.append(
                            ExchangeDeposit(
                                deposit_id=deposit.get("id", ""),
                                symbol=deposit.get("currency", ""),
                                amount=Decimal(deposit.get("amount", "0")),
                                timestamp=datetime.fromtimestamp(int(deposit.get("createdAt", 0)) / 1000),
                                status=status_map.get(deposit.get("status", ""), "unknown"),
                                tx_id=deposit.get("walletTxId"),
                            )
                        )

                    # Check if there are more pages
                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:
            logger.error(f"KuCoin get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from KuCoin."""
        withdrawals = []

        try:
            current_page = 1
            page_size = min(limit, 100)

            async with httpx.AsyncClient() as client:
                while len(withdrawals) < limit:
                    endpoint = f"/api/v1/withdrawals?currentPage={current_page}&pageSize={page_size}"

                    if symbol:
                        endpoint += f"&currency={symbol}"
                    if start_time:
                        endpoint += f"&startAt={int(start_time.timestamp() * 1000)}"

                    headers = self._sign_request("GET", endpoint)

                    response = await client.get(
                        f"{self.BASE_URL}{endpoint}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"KuCoin get_withdrawals error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()

                    if data.get("code") != "200000":
                        logger.error(f"KuCoin get_withdrawals API error: {data.get('msg', 'Unknown error')}")
                        break

                    items = data.get("data", {}).get("items", [])

                    if not items:
                        break

                    for withdrawal in items:
                        if len(withdrawals) >= limit:
                            break

                        status_map = {
                            "PROCESSING": "processing",
                            "WALLET_PROCESSING": "processing",
                            "SUCCESS": "completed",
                            "FAILURE": "failure",
                        }

                        withdrawals.append(
                            ExchangeWithdrawal(
                                withdrawal_id=withdrawal.get("id", ""),
                                symbol=withdrawal.get("currency", ""),
                                amount=Decimal(withdrawal.get("amount", "0")),
                                fee=Decimal(withdrawal.get("fee", "0")),
                                timestamp=datetime.fromtimestamp(int(withdrawal.get("createdAt", 0)) / 1000),
                                status=status_map.get(withdrawal.get("status", ""), "unknown"),
                                tx_id=withdrawal.get("walletTxId"),
                                address=withdrawal.get("address"),
                            )
                        )

                    # Check if there are more pages
                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:
            logger.error(f"KuCoin get_withdrawals error: {e}")

        return withdrawals

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize KuCoin symbol to standard format.

        KuCoin uses standard symbols (BTC, ETH, SOL) so minimal
        normalization is needed. Trading pairs use dash format (BTC-USDT).
        """
        # Handle trading pair format (e.g., "BTC-USDT" -> "BTC")
        if "-" in symbol:
            return symbol.split("-")[0]
        return symbol
