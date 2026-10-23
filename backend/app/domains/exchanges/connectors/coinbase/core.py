import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

logger = logging.getLogger(__name__)


class CoinbaseCore(BaseExchangeService):
    BASE_URL = "https://api.coinbase.com"

    @property
    def exchange_name(self) -> str:
        return "Coinbase"

    def _get_timestamp(self) -> str:
        return str(int(time.time()))

    def _sign_request(self, method: str, request_path: str, body: str = "") -> dict[str, Any]:
        timestamp = self._get_timestamp()
        message = timestamp + method.upper() + request_path + body

        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    async def _get_account_ids(self, symbol: str | None = None) -> list[tuple[str, str]]:
        accounts: list[tuple[str, str]] = []

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

                    if response.status_code != 200:
                        break

                    data = response.json()

                    for account in data.get("accounts", []):
                        currency = account.get("currency", "")
                        if symbol and currency != symbol:
                            continue
                        accounts.append((account.get("uuid", ""), currency))

                    cursor = data.get("cursor")
                    if not cursor or not data.get("has_next", False):
                        break

        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase _get_account_ids error: {e}")

        return accounts
