"""Bitpanda Pro exchange service."""

import logging
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


class BitpandaService(BaseExchangeService):
    """Bitpanda Pro exchange integration.

    Authentication uses a Bearer token (API key only, no secret required).
    API docs: https://developers.bitpanda.com/exchange/
    """

    BASE_URL = "https://api.exchange.bitpanda.com"

    @property
    def exchange_name(self) -> str:
        return "Bitpanda"

    def _get_headers(self) -> dict:
        """Get request headers with Bearer token authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/v1/account/balances",
                    headers=self._get_headers(),
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Bitpanda test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Bitpanda Pro."""
        balances = []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/v1/account/balances",
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                for item in data:
                    available = Decimal(str(item.get("available", "0")))
                    locked = Decimal(str(item.get("locked", "0")))
                    total = available + locked

                    if total > 0:
                        balances.append(
                            ExchangeBalance(
                                symbol=item.get("currency_code", ""),
                                free=available,
                                locked=locked,
                                total=total,
                            )
                        )

        except Exception as e:
            logger.error(f"Bitpanda get_balances error: {e}")

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Bitpanda Pro.

        The API returns paginated results using a cursor.
        """
        trades = []

        try:
            async with httpx.AsyncClient() as client:
                params = {}

                if start_time:
                    params["from"] = start_time.isoformat() + "Z"
                if end_time:
                    params["to"] = end_time.isoformat() + "Z"
                if symbol:
                    params["instrument_code"] = symbol

                collected = 0
                cursor = None

                while collected < limit:
                    request_params = {**params}
                    if cursor:
                        request_params["cursor"] = cursor

                    response = await client.get(
                        f"{self.BASE_URL}/api/v1/account/trades",
                        headers=self._get_headers(),
                        params=request_params,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"Bitpanda get_trades error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()
                    trade_history = data.get("trade_history", [])

                    if not trade_history:
                        break

                    for trade in trade_history:
                        if collected >= limit:
                            break

                        trades.append(
                            ExchangeTrade(
                                trade_id=str(trade.get("trade_id", "")),
                                symbol=trade.get("instrument_code", ""),
                                side=trade.get("side", "").lower(),
                                quantity=Decimal(str(trade.get("amount", "0"))),
                                price=Decimal(str(trade.get("price", "0"))),
                                fee=Decimal(str(trade.get("fee", {}).get("fee_amount", "0"))),
                                fee_currency=trade.get("fee", {}).get("fee_currency", ""),
                                timestamp=datetime.fromisoformat(trade.get("time", "").replace("Z", "+00:00")),
                            )
                        )
                        collected += 1

                    # Check for next page cursor
                    cursor = data.get("cursor")
                    if not cursor:
                        break

        except Exception as e:
            logger.error(f"Bitpanda get_trades error: {e}")

        logger.info(f"Bitpanda: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Bitpanda Pro."""
        deposits = []

        try:
            async with httpx.AsyncClient() as client:
                params = {}

                if symbol:
                    params["currency_code"] = symbol
                if start_time:
                    params["from"] = start_time.isoformat() + "Z"

                response = await client.get(
                    f"{self.BASE_URL}/api/v1/account/deposits",
                    headers=self._get_headers(),
                    params=params,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Bitpanda get_deposits error: {response.status_code} - {response.text[:200]}")
                    return deposits

                data = response.json()
                deposit_history = data.get("deposit_history", data) if isinstance(data, dict) else data

                for deposit in deposit_history[:limit]:
                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=str(deposit.get("transaction_id", "")),
                            symbol=deposit.get("currency_code", ""),
                            amount=Decimal(str(deposit.get("amount", "0"))),
                            timestamp=datetime.fromisoformat(deposit.get("time", "").replace("Z", "+00:00")),
                            status=deposit.get("status", "unknown"),
                            tx_id=deposit.get("blockchain_transaction_id"),
                        )
                    )

        except Exception as e:
            logger.error(f"Bitpanda get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Bitpanda Pro."""
        withdrawals = []

        try:
            async with httpx.AsyncClient() as client:
                params = {}

                if symbol:
                    params["currency_code"] = symbol
                if start_time:
                    params["from"] = start_time.isoformat() + "Z"

                response = await client.get(
                    f"{self.BASE_URL}/api/v1/account/withdrawals",
                    headers=self._get_headers(),
                    params=params,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Bitpanda get_withdrawals error: {response.status_code} - {response.text[:200]}")
                    return withdrawals

                data = response.json()
                withdrawal_history = data.get("withdrawal_history", data) if isinstance(data, dict) else data

                for withdrawal in withdrawal_history[:limit]:
                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=str(withdrawal.get("transaction_id", "")),
                            symbol=withdrawal.get("currency_code", ""),
                            amount=Decimal(str(withdrawal.get("amount", "0"))),
                            fee=Decimal(str(withdrawal.get("fee", "0"))),
                            timestamp=datetime.fromisoformat(withdrawal.get("time", "").replace("Z", "+00:00")),
                            status=withdrawal.get("status", "unknown"),
                            tx_id=withdrawal.get("blockchain_transaction_id"),
                            address=withdrawal.get("recipient_address"),
                        )
                    )

        except Exception as e:
            logger.error(f"Bitpanda get_withdrawals error: {e}")

        return withdrawals
