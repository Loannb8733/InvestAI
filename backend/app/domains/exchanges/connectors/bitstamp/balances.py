import logging
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.bitstamp.core import BitstampCore

logger = logging.getLogger(__name__)


class BitstampBalances(BitstampCore):
    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/balance/"
                headers = self._generate_auth_headers("POST", path)

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp test_connection error: {e}")
            return False

    async def get_balances(self) -> list[ExchangeBalance]:
        """Lit les clés plates `<devise>_balance/_available/_reserved`, devises connues d'abord puis les autres."""
        balances = []

        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/balance/"
                headers = self._generate_auth_headers("POST", path)

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                seen_currencies = set()

                for currency in self.KNOWN_CURRENCIES:
                    balance_key = f"{currency}_balance"
                    available_key = f"{currency}_available"
                    reserved_key = f"{currency}_reserved"

                    if balance_key in data:
                        total = Decimal(str(data.get(balance_key, "0")))
                        available = Decimal(str(data.get(available_key, "0")))
                        reserved = Decimal(str(data.get(reserved_key, "0")))

                        if total > 0:
                            symbol = currency.upper()
                            seen_currencies.add(symbol)
                            balances.append(
                                ExchangeBalance(
                                    symbol=symbol,
                                    free=available,
                                    locked=reserved,
                                    total=total,
                                )
                            )

                for key in data:
                    if key.endswith("_balance"):
                        currency = key.replace("_balance", "").upper()
                        if currency not in seen_currencies:
                            total = Decimal(str(data.get(key, "0")))
                            if total > 0:
                                available = Decimal(str(data.get(f"{currency.lower()}_available", "0")))
                                reserved = Decimal(str(data.get(f"{currency.lower()}_reserved", "0")))
                                balances.append(
                                    ExchangeBalance(
                                        symbol=currency,
                                        free=available,
                                        locked=reserved,
                                        total=total,
                                    )
                                )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp get_balances error: {e}")

        return balances
