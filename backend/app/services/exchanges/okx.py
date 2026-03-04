"""OKX exchange service."""

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
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


class OkxService(BaseExchangeService):
    """OKX exchange integration (API v5)."""

    BASE_URL = "https://www.okx.com"

    @property
    def exchange_name(self) -> str:
        return "OKX"

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO 8601 format for OKX."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _sign_request(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Sign a request with HMAC SHA256 + base64.

        OKX signature: base64(HMAC_SHA256(timestamp + method + requestPath + body))
        """
        pre_sign = f"{timestamp}{method}{request_path}{body}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            pre_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _get_headers(self, timestamp: str, method: str, request_path: str, body: str = "") -> dict:
        """Get request headers with authentication."""
        signature = self._sign_request(timestamp, method, request_path, body)
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase or "",
            "Content-Type": "application/json",
        }

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        """Create HTTP client for OKX API."""
        return httpx.AsyncClient(timeout=timeout)

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            async with self._get_http_client(timeout=15.0) as client:
                request_path = "/api/v5/account/balance"
                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, "GET", request_path)
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                )
                data = response.json()
                return data.get("code") == "0"
        except Exception as e:
            logger.error(f"OKX test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from OKX."""
        balances = []
        try:
            async with self._get_http_client() as client:
                request_path = "/api/v5/account/balance"
                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, "GET", request_path)
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "0":
                    logger.error(f"OKX get_balances error: {data.get('msg')}")
                    return balances

                accounts = data.get("data", [])

                for account in accounts:
                    for detail in account.get("details", []):
                        available = Decimal(detail.get("availBal", "0") or "0")
                        frozen = Decimal(detail.get("frozenBal", "0") or "0")
                        total = available + frozen

                        if total > 0:
                            balances.append(
                                ExchangeBalance(
                                    symbol=detail.get("ccy", ""),
                                    free=available,
                                    locked=frozen,
                                    total=total,
                                )
                            )

        except Exception as e:
            logger.error(f"OKX get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from OKX."""
        all_trades = []
        try:
            async with self._get_http_client() as client:
                after = ""
                fetched = 0

                while fetched < limit:
                    request_path = "/api/v5/trade/fills-history?instType=SPOT"
                    if symbol:
                        request_path += f"&instId={symbol}"
                    if start_time:
                        request_path += f"&begin={int(start_time.timestamp() * 1000)}"
                    if end_time:
                        request_path += f"&end={int(end_time.timestamp() * 1000)}"
                    request_path += f"&limit={min(limit - fetched, 100)}"
                    if after:
                        request_path += f"&after={after}"

                    timestamp = self._get_timestamp()
                    headers = self._get_headers(timestamp, "GET", request_path)
                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data.get("code") != "0":
                        logger.error(f"OKX get_trades error: {data.get('msg')}")
                        break

                    trades_list = data.get("data", [])

                    if not trades_list:
                        break

                    for trade in trades_list:
                        side = trade.get("side", "").lower()
                        ts = trade.get("ts", "0")
                        all_trades.append(
                            ExchangeTrade(
                                trade_id=trade.get("tradeId", ""),
                                symbol=trade.get("instId", ""),
                                side=side if side in ("buy", "sell") else "buy",
                                quantity=Decimal(trade.get("fillSz", "0")),
                                price=Decimal(trade.get("fillPx", "0")),
                                fee=abs(Decimal(trade.get("fee", "0"))),
                                fee_currency=trade.get("feeCcy", ""),
                                timestamp=datetime.fromtimestamp(int(ts) / 1000),
                            )
                        )
                        fetched += 1

                    # Use the last billId for pagination (OKX uses billId as cursor)
                    last_bill_id = trades_list[-1].get("billId", "")
                    if not last_bill_id:
                        break
                    after = last_bill_id

        except Exception as e:
            logger.error(f"OKX get_trades error: {e}")

        logger.info(f"OKX: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from OKX."""
        deposits = []
        try:
            async with self._get_http_client() as client:
                request_path = "/api/v5/asset/deposit-history"
                query_parts = []
                if symbol:
                    query_parts.append(f"ccy={symbol}")
                if start_time:
                    query_parts.append(f"after={int(start_time.timestamp() * 1000)}")
                query_parts.append(f"limit={min(limit, 100)}")

                if query_parts:
                    request_path += "?" + "&".join(query_parts)

                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, "GET", request_path)
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "0":
                    logger.error(f"OKX get_deposits error: {data.get('msg')}")
                    return deposits

                # OKX deposit status mapping
                status_map = {
                    "0": "pending",
                    "1": "pending",
                    "2": "success",
                    "8": "pending",
                    "11": "failed",
                    "12": "failed",
                }

                for deposit in data.get("data", []):
                    dep_status = deposit.get("state", "")
                    ts = deposit.get("ts", "0")
                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=deposit.get("depId", ""),
                            symbol=deposit.get("ccy", ""),
                            amount=Decimal(deposit.get("amt", "0")),
                            timestamp=datetime.fromtimestamp(int(ts) / 1000),
                            status=status_map.get(dep_status, "unknown"),
                            tx_id=deposit.get("txId"),
                        )
                    )

        except Exception as e:
            logger.error(f"OKX get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from OKX."""
        withdrawals = []
        try:
            async with self._get_http_client() as client:
                request_path = "/api/v5/asset/withdrawal-history"
                query_parts = []
                if symbol:
                    query_parts.append(f"ccy={symbol}")
                if start_time:
                    query_parts.append(f"after={int(start_time.timestamp() * 1000)}")
                query_parts.append(f"limit={min(limit, 100)}")

                if query_parts:
                    request_path += "?" + "&".join(query_parts)

                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, "GET", request_path)
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "0":
                    logger.error(f"OKX get_withdrawals error: {data.get('msg')}")
                    return withdrawals

                # OKX withdrawal status mapping
                status_map = {
                    "-3": "pending",
                    "-2": "cancelled",
                    "-1": "failed",
                    "0": "pending",
                    "1": "pending",
                    "2": "completed",
                    "7": "approved",
                    "10": "pending",
                }

                for withdrawal in data.get("data", []):
                    w_status = withdrawal.get("state", "")
                    ts = withdrawal.get("ts", "0")
                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=withdrawal.get("wdId", ""),
                            symbol=withdrawal.get("ccy", ""),
                            amount=Decimal(withdrawal.get("amt", "0")),
                            fee=Decimal(withdrawal.get("fee", "0")),
                            timestamp=datetime.fromtimestamp(int(ts) / 1000),
                            status=status_map.get(w_status, "unknown"),
                            tx_id=withdrawal.get("txId"),
                            address=withdrawal.get("to"),
                        )
                    )

        except Exception as e:
            logger.error(f"OKX get_withdrawals error: {e}")

        return withdrawals
