"""Gate.io exchange service."""

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


class GateIOService(BaseExchangeService):
    """Gate.io exchange integration.

    Authentication uses HMAC SHA512 signatures.
    API docs: https://www.gate.io/docs/developers/apiv4/
    """

    BASE_URL = "https://api.gateio.ws"

    @property
    def exchange_name(self) -> str:
        return "Gate.io"

    def _sign_request(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
    ) -> dict:
        """Generate authentication headers for Gate.io API v4.

        Signature payload format:
            method + \n + path + \n + query + \n + hex(sha512(body)) + \n + timestamp
        """
        timestamp = str(int(time.time()))

        # Hash the body with SHA512
        body_hash = hashlib.sha512(body.encode("utf-8")).hexdigest()

        # Build the signature string
        sign_string = f"{method}\n{path}\n{query}\n{body_hash}\n{timestamp}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        return {
            "KEY": self.api_key,
            "SIGN": signature,
            "Timestamp": timestamp,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v4/spot/accounts"
                headers = self._sign_request("GET", path)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Gate.io test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Gate.io."""
        balances = []

        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v4/spot/accounts"
                headers = self._sign_request("GET", path)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                for account in data:
                    available = Decimal(str(account.get("available", "0")))
                    locked = Decimal(str(account.get("locked", "0")))
                    total = available + locked

                    if total > 0:
                        balances.append(
                            ExchangeBalance(
                                symbol=account.get("currency", ""),
                                free=available,
                                locked=locked,
                                total=total,
                            )
                        )

        except Exception as e:
            logger.error(f"Gate.io get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Gate.io.

        If no symbol is provided, fetches trades for all currency pairs
        based on current balances.
        """
        trades = []

        try:
            # Determine which currency pairs to query
            if symbol:
                pairs = [symbol]
            else:
                # Get pairs from balances
                pairs = await self._get_trading_pairs_from_balances()

            async with httpx.AsyncClient() as client:
                for pair in pairs:
                    pair_trades = await self._fetch_trades_for_pair(
                        client, pair, start_time, end_time, limit - len(trades)
                    )
                    trades.extend(pair_trades)

                    if len(trades) >= limit:
                        break

        except Exception as e:
            logger.error(f"Gate.io get_trades error: {e}")

        logger.info(f"Gate.io: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)[:limit]

    async def _get_trading_pairs_from_balances(self) -> List[str]:
        """Build list of trading pairs from current balances."""
        pairs = []
        quote_currencies = ["USDT", "USD", "BTC", "ETH"]
        fiat_currencies = {"USD", "EUR", "GBP", "USDT", "USDC"}

        try:
            balances = await self.get_balances()
            for balance in balances:
                if balance.symbol in fiat_currencies:
                    continue
                for quote in quote_currencies:
                    if balance.symbol != quote:
                        pairs.append(f"{balance.symbol}_{quote}")
        except Exception as e:
            logger.error(f"Gate.io error building trading pairs: {e}")

        return pairs

    async def _fetch_trades_for_pair(
        self,
        client: httpx.AsyncClient,
        currency_pair: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
    ) -> List[ExchangeTrade]:
        """Fetch trades for a single currency pair with pagination."""
        trades = []
        page = 1
        page_size = min(limit, 100)

        while len(trades) < limit:
            try:
                path = "/api/v4/spot/my_trades"
                query_params = {
                    "currency_pair": currency_pair,
                    "limit": str(page_size),
                    "page": str(page),
                }

                if start_time:
                    query_params["from"] = str(int(start_time.timestamp()))
                if end_time:
                    query_params["to"] = str(int(end_time.timestamp()))

                query_string = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
                headers = self._sign_request("GET", path, query=query_string)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    params=query_params,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    break

                data = response.json()

                if not data:
                    break

                for trade in data:
                    if len(trades) >= limit:
                        break

                    trades.append(
                        ExchangeTrade(
                            trade_id=str(trade.get("id", "")),
                            symbol=trade.get("currency_pair", currency_pair),
                            side=trade.get("side", "").lower(),
                            quantity=Decimal(str(trade.get("amount", "0"))),
                            price=Decimal(str(trade.get("price", "0"))),
                            fee=Decimal(str(trade.get("fee", "0"))),
                            fee_currency=trade.get("fee_currency", ""),
                            timestamp=datetime.fromtimestamp(int(trade.get("create_time", 0))),
                        )
                    )

                # If we got fewer results than page size, no more pages
                if len(data) < page_size:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Gate.io error fetching trades for {currency_pair}: {e}")
                break

        return trades

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Gate.io."""
        deposits = []

        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v4/wallet/deposits"
                query_params = {
                    "limit": str(min(limit, 100)),
                }

                if symbol:
                    query_params["currency"] = symbol
                if start_time:
                    query_params["from"] = str(int(start_time.timestamp()))

                query_string = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
                headers = self._sign_request("GET", path, query=query_string)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    params=query_params,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Gate.io get_deposits error: {response.status_code} - {response.text[:200]}")
                    return deposits

                data = response.json()

                for deposit in data[:limit]:
                    status_map = {
                        "DONE": "completed",
                        "CANCEL": "cancelled",
                        "REQUEST": "pending",
                        "MANUAL": "pending",
                        "BCODE": "completed",
                    }

                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=str(deposit.get("id", "")),
                            symbol=deposit.get("currency", ""),
                            amount=Decimal(str(deposit.get("amount", "0"))),
                            timestamp=datetime.fromtimestamp(int(deposit.get("timestamp", 0))),
                            status=status_map.get(deposit.get("status", ""), "unknown"),
                            tx_id=deposit.get("txid"),
                        )
                    )

        except Exception as e:
            logger.error(f"Gate.io get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Gate.io."""
        withdrawals = []

        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v4/wallet/withdrawals"
                query_params = {
                    "limit": str(min(limit, 100)),
                }

                if symbol:
                    query_params["currency"] = symbol
                if start_time:
                    query_params["from"] = str(int(start_time.timestamp()))

                query_string = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
                headers = self._sign_request("GET", path, query=query_string)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    params=query_params,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Gate.io get_withdrawals error: {response.status_code} - {response.text[:200]}")
                    return withdrawals

                data = response.json()

                for withdrawal in data[:limit]:
                    status_map = {
                        "DONE": "completed",
                        "CANCEL": "cancelled",
                        "REQUEST": "pending",
                        "MANUAL": "pending",
                        "BCODE": "completed",
                        "EXTPEND": "pending",
                        "FAIL": "failed",
                        "INVALID": "failed",
                        "VERIFY": "pending",
                        "PROCES": "processing",
                        "PEND": "pending",
                        "DMOVE": "processing",
                    }

                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=str(withdrawal.get("id", "")),
                            symbol=withdrawal.get("currency", ""),
                            amount=Decimal(str(withdrawal.get("amount", "0"))),
                            fee=Decimal(str(withdrawal.get("fee", "0"))),
                            timestamp=datetime.fromtimestamp(int(withdrawal.get("timestamp", 0))),
                            status=status_map.get(withdrawal.get("status", ""), "unknown"),
                            tx_id=withdrawal.get("txid"),
                            address=withdrawal.get("address"),
                        )
                    )

        except Exception as e:
            logger.error(f"Gate.io get_withdrawals error: {e}")

        return withdrawals
