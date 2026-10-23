import logging
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.cryptocom.core import CryptoComCore

logger = logging.getLogger(__name__)


class CryptoComBalances(CryptoComCore):
    async def test_connection(self) -> bool:
        try:
            result = await self._make_request("private/get-account-summary")
            return result.get("code") == 0
        except Exception:  # noqa: BLE001
            return False

    async def get_balances(self) -> list[ExchangeBalance]:
        balances: list[ExchangeBalance] = []

        try:
            result = await self._make_request("private/get-account-summary")

            if result.get("code") != 0:
                return balances

            accounts = result.get("result", {}).get("accounts", [])

            for account in accounts:
                balance = Decimal(str(account.get("balance", 0)))
                available = Decimal(str(account.get("available", 0)))

                if balance > 0:
                    balances.append(
                        ExchangeBalance(
                            symbol=account["currency"],
                            free=available,
                            locked=balance - available,
                            total=balance,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Crypto.com: failed to fetch balances: %s", exc)

        return balances
