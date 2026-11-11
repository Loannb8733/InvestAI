import base64
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

UNKNOWN_KEY = "50119"


def _unknown_key(response: httpx.Response) -> bool:
    try:
        return bool(response.json().get("code") == UNKNOWN_KEY)
    except ValueError:
        return False


class OkxCore(BaseExchangeService):
    """Signature et domaine des requêtes OKX v5 : www.okx.com, ou eea.okx.com pour l'EEE."""

    BASE_URLS = ("https://www.okx.com", "https://eea.okx.com")
    _base_url = BASE_URLS[0]

    @property
    def exchange_name(self) -> str:
        return "OKX"

    def _get_timestamp(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _sign_request(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        pre_sign = f"{timestamp}{method}{request_path}{body}"
        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            pre_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _get_headers(self, timestamp: str, method: str, request_path: str, body: str = "") -> dict[str, Any]:
        signature = self._sign_request(timestamp, method, request_path, body)
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase or "",
            "Content-Type": "application/json",
        }

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    async def _signed_get(self, client: httpx.AsyncClient, base_url: str, request_path: str) -> httpx.Response:
        headers = self._get_headers(self._get_timestamp(), "GET", request_path)
        return await client.get(f"{base_url}{request_path}", headers=headers)

    async def _get(self, client: httpx.AsyncClient, request_path: str) -> httpx.Response:
        """GET signé ; une clé inconnue du domaine courant est essayée sur l'autre (eea.okx.com pour les comptes
        de l'Espace économique européen), qui est alors retenu."""
        response = await self._signed_get(client, self._base_url, request_path)
        if not _unknown_key(response):
            return response
        other = next(url for url in self.BASE_URLS if url != self._base_url)
        retry = await self._signed_get(client, other, request_path)
        if _unknown_key(retry):
            return response
        self._base_url = other
        return retry
