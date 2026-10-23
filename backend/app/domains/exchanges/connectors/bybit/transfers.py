import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.bybit.core import BybitCore

logger = logging.getLogger(__name__)


class BybitTransfers(BybitCore):
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []
        try:
            async with self._get_http_client() as client:
                params: dict[str, Any] = {
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
                            timestamp=(
                                datetime.fromtimestamp(int(success_time) / 1000, tz=UTC)
                                if int(success_time) > 0
                                else datetime.now()
                            ),
                            status=status_map.get(dep_status, "unknown"),
                            tx_id=deposit.get("txID"),
                        )
                    )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bybit get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []
        try:
            async with self._get_http_client() as client:
                params: dict[str, Any] = {
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
                            timestamp=(
                                datetime.fromtimestamp(int(create_time) / 1000, tz=UTC)
                                if int(create_time) > 0
                                else datetime.now()
                            ),
                            status=status_map.get(w_status, "unknown"),
                            tx_id=withdrawal.get("txID"),
                            address=withdrawal.get("toAddress"),
                        )
                    )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bybit get_withdrawals error: {e}")

        return withdrawals
