"""Bybit exchange service."""

import hashlib
import hmac
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class BybitService(BaseExchangeService):
    """Bybit exchange integration (API v5)."""

    BASE_URL = "https://api.bybit.com"
    RECV_WINDOW = "5000"

    @property
    def exchange_name(self) -> str:
        return "Bybit"

    def _get_timestamp(self) -> str:
        """Get current timestamp in milliseconds."""
        return str(int(time.time() * 1000))

    def _sign_request(self, timestamp: str, params: dict) -> str:
        """Sign a request with HMAC SHA256.

        Bybit v5 signature: HMAC_SHA256(timestamp + api_key + recv_window + queryString)
        """
        query_string = urlencode(params) if params else ""
        pre_sign = f"{timestamp}{self.api_key}{self.RECV_WINDOW}{query_string}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            pre_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_headers(self, timestamp: str, params: dict) -> dict:
        """Get request headers with authentication."""
        signature = self._sign_request(timestamp, params)
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.RECV_WINDOW,
        }

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        """Create HTTP client for Bybit API."""
        return httpx.AsyncClient(timeout=timeout)

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            async with self._get_http_client(timeout=15.0) as client:
                params = {"accountType": "UNIFIED"}
                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, params)
                response = await client.get(
                    f"{self.BASE_URL}/v5/account/wallet-balance",
                    params=params,
                    headers=headers,
                )
                data = response.json()
                return data.get("retCode") == 0
        except Exception as e:
            logger.error(f"Bybit test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Bybit."""
        balances = []
        try:
            async with self._get_http_client() as client:
                params = {"accountType": "UNIFIED"}
                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, params)
                response = await client.get(
                    f"{self.BASE_URL}/v5/account/wallet-balance",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("retCode") != 0:
                    logger.error(f"Bybit get_balances error: {data.get('retMsg')}")
                    return balances

                result = data.get("result", {})
                accounts = result.get("list", [])

                for account in accounts:
                    for coin in account.get("coin", []):
                        free = Decimal(coin.get("availableToWithdraw", "0"))
                        locked = Decimal(coin.get("locked", "0"))
                        total = Decimal(coin.get("walletBalance", "0"))

                        if total > 0:
                            balances.append(
                                ExchangeBalance(
                                    symbol=coin.get("coin", ""),
                                    free=free,
                                    locked=locked,
                                    total=total,
                                )
                            )

        except Exception as e:
            logger.error(f"Bybit get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Bybit using cursor-based pagination."""
        all_trades = []
        try:
            async with self._get_http_client() as client:
                cursor = None
                fetched = 0

                while fetched < limit:
                    params: dict = {
                        "category": "spot",
                        "limit": str(min(limit - fetched, 100)),
                    }
                    if symbol:
                        params["symbol"] = symbol
                    if start_time:
                        params["startTime"] = str(int(start_time.timestamp() * 1000))
                    if end_time:
                        params["endTime"] = str(int(end_time.timestamp() * 1000))
                    if cursor:
                        params["cursor"] = cursor

                    timestamp = self._get_timestamp()
                    headers = self._get_headers(timestamp, params)
                    response = await client.get(
                        f"{self.BASE_URL}/v5/execution/list",
                        params=params,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data.get("retCode") != 0:
                        logger.error(f"Bybit get_trades error: {data.get('retMsg')}")
                        break

                    result = data.get("result", {})
                    trades_list = result.get("list", [])

                    if not trades_list:
                        break

                    for trade in trades_list:
                        side = trade.get("side", "").lower()
                        exec_time = trade.get("execTime", "0")
                        all_trades.append(
                            ExchangeTrade(
                                trade_id=trade.get("execId", ""),
                                symbol=trade.get("symbol", ""),
                                side=side if side in ("buy", "sell") else "buy",
                                quantity=Decimal(trade.get("execQty", "0")),
                                price=Decimal(trade.get("execPrice", "0")),
                                fee=Decimal(trade.get("execFee", "0")),
                                fee_currency=trade.get("feeCurrency", ""),
                                timestamp=datetime.fromtimestamp(int(exec_time) / 1000),
                            )
                        )
                        fetched += 1

                    # Check for next page cursor
                    next_cursor = result.get("nextPageCursor", "")
                    if not next_cursor:
                        break
                    cursor = next_cursor

        except Exception as e:
            logger.error(f"Bybit get_trades error: {e}")

        logger.info(f"Bybit: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Bybit."""
        deposits = []
        try:
            async with self._get_http_client() as client:
                params: dict = {
                    "limit": str(min(limit, 50)),
                }
                if symbol:
                    params["coin"] = symbol
                if start_time:
                    params["startTime"] = str(int(start_time.timestamp() * 1000))

                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, params)
                response = await client.get(
                    f"{self.BASE_URL}/v5/asset/deposit/query-record",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("retCode") != 0:
                    logger.error(f"Bybit get_deposits error: {data.get('retMsg')}")
                    return deposits

                result = data.get("result", {})
                rows = result.get("rows", [])

                # Bybit deposit status mapping
                status_map = {
                    0: "unknown",
                    1: "pending",
                    2: "pending",
                    3: "success",
                    4: "failed",
                }

                for deposit in rows:
                    dep_status = deposit.get("status", 0)
                    success_time = deposit.get("successAt", "0")
                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=deposit.get("id", ""),
                            symbol=deposit.get("coin", ""),
                            amount=Decimal(deposit.get("amount", "0")),
                            timestamp=datetime.fromtimestamp(int(success_time) / 1000)
                            if int(success_time) > 0
                            else datetime.now(),
                            status=status_map.get(dep_status, "unknown"),
                            tx_id=deposit.get("txID"),
                        )
                    )

        except Exception as e:
            logger.error(f"Bybit get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Bybit."""
        withdrawals = []
        try:
            async with self._get_http_client() as client:
                params: dict = {
                    "limit": str(min(limit, 50)),
                }
                if symbol:
                    params["coin"] = symbol
                if start_time:
                    params["startTime"] = str(int(start_time.timestamp() * 1000))

                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, params)
                response = await client.get(
                    f"{self.BASE_URL}/v5/asset/withdraw/query-record",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("retCode") != 0:
                    logger.error(f"Bybit get_withdrawals error: {data.get('retMsg')}")
                    return withdrawals

                result = data.get("result", {})
                rows = result.get("rows", [])

                # Bybit withdrawal status mapping
                status_map = {
                    "SecurityCheck": "pending",
                    "Pending": "pending",
                    "success": "completed",
                    "CancelByUser": "cancelled",
                    "Reject": "rejected",
                    "Fail": "failure",
                    "BlockchainConfirmed": "completed",
                }

                for withdrawal in rows:
                    w_status = withdrawal.get("status", "")
                    create_time = withdrawal.get("createTime", "0")
                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=withdrawal.get("withdrawId", ""),
                            symbol=withdrawal.get("coin", ""),
                            amount=Decimal(withdrawal.get("amount", "0")),
                            fee=Decimal(withdrawal.get("withdrawFee", "0")),
                            timestamp=datetime.fromtimestamp(int(create_time) / 1000)
                            if int(create_time) > 0
                            else datetime.now(),
                            status=status_map.get(w_status, "unknown"),
                            tx_id=withdrawal.get("txID"),
                            address=withdrawal.get("toAddress"),
                        )
                    )

        except Exception as e:
            logger.error(f"Bybit get_withdrawals error: {e}")

        return withdrawals
