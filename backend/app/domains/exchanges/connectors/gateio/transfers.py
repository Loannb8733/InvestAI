import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.gateio.core import GateIOCore

logger = logging.getLogger(__name__)


class GateIOTransfers(GateIOCore):
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []

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
                            timestamp=datetime.fromtimestamp(int(deposit.get("timestamp", 0)), tz=UTC),
                            status=status_map.get(deposit.get("status", ""), "unknown"),
                            tx_id=deposit.get("txid"),
                        )
                    )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []

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
                            timestamp=datetime.fromtimestamp(int(withdrawal.get("timestamp", 0)), tz=UTC),
                            status=status_map.get(withdrawal.get("status", ""), "unknown"),
                            tx_id=withdrawal.get("txid"),
                            address=withdrawal.get("address"),
                        )
                    )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io get_withdrawals error: {e}")

        return withdrawals
