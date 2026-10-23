import hashlib
import hmac
import time
from typing import Any, ClassVar

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService


class CryptoComCore(BaseExchangeService):
    BASE_URL = "https://api.crypto.com/v2"
    QUOTE_CURRENCIES: ClassVar[list[str]] = ["USDT", "USD", "EUR", "BTC", "CRO"]
    FIAT_CURRENCIES: ClassVar[list[str]] = ["EUR", "USD", "GBP", "AUD", "CAD", "SGD"]

    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=30.0)
        return cls._client

    @property
    def exchange_name(self) -> str:
        return "Crypto.com"

    def _sign_request(self, method: str, request_id: str, params: dict[str, Any], nonce: str) -> str:
        param_string = ""
        if params:
            sorted_params = sorted(params.items())
            param_string = "".join(f"{k}{v}" for k, v in sorted_params)

        sig_payload = f"{method}{request_id}{self.api_key}{param_string}{nonce}"

        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            sig_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    async def _make_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = str(int(time.time() * 1000))
        nonce = str(int(time.time() * 1000))

        if params is None:
            params = {}

        signature = self._sign_request(method, request_id, params, nonce)

        payload = {
            "id": request_id,
            "method": method,
            "api_key": self.api_key,
            "params": params,
            "sig": signature,
            "nonce": nonce,
        }

        response = await self._get_client().post(
            f"{self.BASE_URL}/{method}",
            json=payload,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
