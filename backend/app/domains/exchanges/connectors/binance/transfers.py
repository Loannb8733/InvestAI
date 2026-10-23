from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.binance.core import BinanceCore


class BinanceTransfers(BinanceCore):
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []

        await self._sync_server_time()

        async with self._get_http_client() as client:
            params: dict[str, Any] = {}
            if symbol:
                params["coin"] = symbol
            if start_time:
                params["startTime"] = int(start_time.timestamp() * 1000)

            params = self._sign_request(params)
            response = await self._api_get(
                client,
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
                        timestamp=datetime.fromtimestamp(deposit["insertTime"] / 1000, tz=UTC),
                        status=status_map.get(deposit["status"], "unknown"),
                        tx_id=deposit.get("txId"),
                    )
                )

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []

        await self._sync_server_time()

        async with self._get_http_client() as client:
            params: dict[str, Any] = {}
            if symbol:
                params["coin"] = symbol
            if start_time:
                params["startTime"] = int(start_time.timestamp() * 1000)

            params = self._sign_request(params)
            response = await self._api_get(
                client,
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
                        timestamp=datetime.fromisoformat(withdrawal["applyTime"].replace("Z", "+00:00")),
                        status=status_map.get(withdrawal["status"], "unknown"),
                        tx_id=withdrawal.get("txId"),
                        address=withdrawal.get("address"),
                    )
                )

        return withdrawals
