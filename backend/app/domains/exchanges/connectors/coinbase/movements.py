import logging
from datetime import datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.coinbase.core import CoinbaseCore

logger = logging.getLogger(__name__)


class CoinbaseMovements(CoinbaseCore):
    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        """Parcourt les transactions de type dépôt de chaque compte, avec repli sur l'API v2 en cas d'échec."""
        deposits: list[ExchangeDeposit] = []

        try:
            accounts = await self._get_account_ids(symbol)

            async with httpx.AsyncClient() as client:
                for account_id, currency in accounts:
                    if len(deposits) >= limit:
                        break

                    request_path = f"/api/v3/brokerage/accounts/{account_id}/transactions?limit=100&type=deposit"
                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        request_path_v2 = f"/v2/accounts/{account_id}/deposits"
                        headers_v2 = self._sign_request("GET", request_path_v2)

                        response = await client.get(
                            f"{self.BASE_URL}{request_path_v2}",
                            headers=headers_v2,
                            timeout=30.0,
                        )

                        if response.status_code != 200:
                            continue

                    data = response.json()
                    transactions = data.get("transactions", data.get("data", []))

                    for tx in transactions:
                        if len(deposits) >= limit:
                            break

                        tx_time = tx.get("created_at", tx.get("payout_at", ""))
                        if tx_time:
                            tx_datetime = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
                            if start_time and tx_datetime < start_time:
                                continue
                        else:
                            tx_datetime = datetime.now()

                        amount_data = tx.get("amount", {})
                        amount = Decimal(amount_data.get("value", amount_data.get("amount", "0")))

                        deposits.append(
                            ExchangeDeposit(
                                deposit_id=tx.get("id", ""),
                                symbol=amount_data.get("currency", currency),
                                amount=abs(amount),
                                timestamp=tx_datetime,
                                status=tx.get("status", "completed"),
                                tx_id=tx.get("network", {}).get("hash"),
                            )
                        )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        """Parcourt les transactions de type retrait de chaque compte, avec repli sur l'API v2 en cas d'échec."""
        withdrawals: list[ExchangeWithdrawal] = []

        try:
            accounts = await self._get_account_ids(symbol)

            async with httpx.AsyncClient() as client:
                for account_id, currency in accounts:
                    if len(withdrawals) >= limit:
                        break

                    request_path = f"/api/v3/brokerage/accounts/{account_id}/transactions?limit=100&type=withdrawal"
                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        request_path_v2 = f"/v2/accounts/{account_id}/withdrawals"
                        headers_v2 = self._sign_request("GET", request_path_v2)

                        response = await client.get(
                            f"{self.BASE_URL}{request_path_v2}",
                            headers=headers_v2,
                            timeout=30.0,
                        )

                        if response.status_code != 200:
                            continue

                    data = response.json()
                    transactions = data.get("transactions", data.get("data", []))

                    for tx in transactions:
                        if len(withdrawals) >= limit:
                            break

                        tx_time = tx.get("created_at", tx.get("payout_at", ""))
                        if tx_time:
                            tx_datetime = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
                            if start_time and tx_datetime < start_time:
                                continue
                        else:
                            tx_datetime = datetime.now()

                        amount_data = tx.get("amount", {})
                        amount = Decimal(amount_data.get("value", amount_data.get("amount", "0")))
                        fee_data = tx.get("fee", {})
                        fee = Decimal(fee_data.get("value", fee_data.get("amount", "0")))

                        network_data = tx.get("network", {})

                        withdrawals.append(
                            ExchangeWithdrawal(
                                withdrawal_id=tx.get("id", ""),
                                symbol=amount_data.get("currency", currency),
                                amount=abs(amount),
                                fee=abs(fee),
                                timestamp=tx_datetime,
                                status=tx.get("status", "completed"),
                                tx_id=network_data.get("hash"),
                                address=network_data.get("to_address_info", {}).get("address"),
                            )
                        )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase get_withdrawals error: {e}")

        return withdrawals
