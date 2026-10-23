import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.cryptocom.core import CryptoComCore

logger = logging.getLogger(__name__)


class CryptoComMovements(CryptoComCore):
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []

        try:
            params: dict[str, Any] = {"page_size": min(limit, 200)}

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
                        timestamp=datetime.fromtimestamp(deposit["create_time"] / 1000, tz=UTC),
                        status=status_map.get(deposit.get("status", 0), "unknown"),
                        tx_id=deposit.get("txid"),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Crypto.com: failed to fetch deposit history: %s", exc)

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []

        try:
            params: dict[str, Any] = {"page_size": min(limit, 200)}

            if symbol:
                params["currency"] = symbol
            if start_time:
                params["start_ts"] = int(start_time.timestamp() * 1000)

            result = await self._make_request("private/get-withdrawal-history", params)

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
                        timestamp=datetime.fromtimestamp(withdrawal["create_time"] / 1000, tz=UTC),
                        status=status_map.get(withdrawal.get("status", 0), "unknown"),
                        tx_id=withdrawal.get("txid"),
                        address=withdrawal.get("address"),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Crypto.com: failed to fetch withdrawal history: %s", exc)

        return withdrawals
