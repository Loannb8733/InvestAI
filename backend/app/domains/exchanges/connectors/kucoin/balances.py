import logging
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.kucoin.core import KuCoinCore

logger = logging.getLogger(__name__)


class KuCoinBalances(KuCoinCore):
    async def test_connection(self) -> bool:
        try:
            endpoint = "/api/v1/accounts"
            headers = self._sign_request("GET", endpoint)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=15.0,
                )
                data = response.json()
                connected: bool = data.get("code") == "200000"
                return connected
        except Exception as e:  # noqa: BLE001
            logger.error(f"KuCoin test_connection error: {e}")
            return False

    async def get_balances(self) -> list[ExchangeBalance]:
        """Soldes non nuls du seul compte de type « trade »."""
        balances: list[ExchangeBalance] = []

        try:
            endpoint = "/api/v1/accounts?type=trade"
            headers = self._sign_request("GET", endpoint)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{endpoint}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != "200000":
                    logger.error(f"KuCoin get_balances error: {data.get('msg', 'Unknown error')}")
                    return balances

                for account in data.get("data", []):
                    available = Decimal(account.get("available", "0"))
                    holds = Decimal(account.get("holds", "0"))
                    total = available + holds

                    if total > 0:
                        balances.append(
                            ExchangeBalance(
                                symbol=account.get("currency", ""),
                                free=available,
                                locked=holds,
                                total=total,
                            )
                        )

        except Exception as e:  # noqa: BLE001
            logger.error(f"KuCoin get_balances error: {e}")

        return balances
