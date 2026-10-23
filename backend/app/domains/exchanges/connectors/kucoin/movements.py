import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.kucoin.core import KuCoinCore

logger = logging.getLogger(__name__)


class KuCoinMovements(KuCoinCore):
    async def get_deposits(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []

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
                                timestamp=datetime.fromtimestamp(int(deposit.get("createdAt", 0)) / 1000, tz=UTC),
                                status=status_map.get(deposit.get("status", ""), "unknown"),
                                tx_id=deposit.get("walletTxId"),
                            )
                        )

                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:  # noqa: BLE001
            logger.error(f"KuCoin get_deposits error: {e}")

        return deposits

    async def get_withdrawals(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []

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
                                timestamp=datetime.fromtimestamp(int(withdrawal.get("createdAt", 0)) / 1000, tz=UTC),
                                status=status_map.get(withdrawal.get("status", ""), "unknown"),
                                tx_id=withdrawal.get("walletTxId"),
                                address=withdrawal.get("address"),
                            )
                        )

                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:  # noqa: BLE001
            logger.error(f"KuCoin get_withdrawals error: {e}")

        return withdrawals
