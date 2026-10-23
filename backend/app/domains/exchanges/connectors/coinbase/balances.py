import logging
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.coinbase.core import CoinbaseCore

logger = logging.getLogger(__name__)


class CoinbaseBalances(CoinbaseCore):
    async def test_connection(self) -> bool:
        try:
            request_path = "/api/v3/brokerage/accounts?limit=1"
            headers = self._sign_request("GET", request_path)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{request_path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase test_connection error: {e}")
            return False

    async def get_balances(self) -> list[ExchangeBalance]:
        balances: list[ExchangeBalance] = []

        try:
            cursor: str | None = None

            async with httpx.AsyncClient() as client:
                while True:
                    request_path = "/api/v3/brokerage/accounts?limit=250"
                    if cursor:
                        request_path += f"&cursor={cursor}"

                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    for account in data.get("accounts", []):
                        available = Decimal(account.get("available_balance", {}).get("value", "0"))
                        hold = Decimal(account.get("hold", {}).get("value", "0"))
                        total = available + hold

                        if total > 0:
                            balances.append(
                                ExchangeBalance(
                                    symbol=account.get("currency", ""),
                                    free=available,
                                    locked=hold,
                                    total=total,
                                )
                            )

                    cursor = data.get("cursor")
                    if not cursor or not data.get("has_next", False):
                        break

        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase get_balances error: {e}")

        return balances
