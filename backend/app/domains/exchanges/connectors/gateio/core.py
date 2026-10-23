import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

logger = logging.getLogger(__name__)


class GateIOCore(BaseExchangeService):
    """Connecteur Gate.io (API v4, signatures HMAC SHA512)."""

    BASE_URL = "https://api.gateio.ws"

    @property
    def exchange_name(self) -> str:
        return "Gate.io"

    def _sign_request(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
    ) -> dict[str, Any]:
        timestamp = str(int(time.time()))

        body_hash = hashlib.sha512(body.encode("utf-8")).hexdigest()

        sign_string = f"{method}\n{path}\n{query}\n{body_hash}\n{timestamp}"

        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        return {
            "KEY": self.api_key,
            "SIGN": signature,
            "Timestamp": timestamp,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v4/spot/accounts"
                headers = self._sign_request("GET", path)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io test_connection error: {e}")
            return False
