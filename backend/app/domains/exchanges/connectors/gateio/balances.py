import logging
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.gateio.core import GateIOCore

logger = logging.getLogger(__name__)


class GateIOBalances(GateIOCore):
    async def get_balances(self) -> list[ExchangeBalance]:
        balances: list[ExchangeBalance] = []

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

        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io get_balances error: {e}")

        return balances
