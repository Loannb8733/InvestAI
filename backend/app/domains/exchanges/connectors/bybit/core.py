import hashlib
import hmac
import logging
import time
from typing import Any, ClassVar
from urllib.parse import urlencode

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

logger = logging.getLogger(__name__)


class BybitCore(BaseExchangeService):
    """Connecteur Bybit (API v5) : domaine global d'abord, domaine européen en repli."""

    BASE_URLS: ClassVar[list[str]] = ["https://api.bybit.com", "https://api.bybit.nl"]
    RECV_WINDOW = "5000"

    def __init__(self, api_key: str, secret_key: str, passphrase: str | None = None) -> None:
        super().__init__(api_key, secret_key, passphrase)
        self._base_url: str | None = None

    @property
    def exchange_name(self) -> str:
        return "Bybit"

    def _get_timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign_request(self, timestamp: str, params: dict[str, Any]) -> str:
        query_string = urlencode(params) if params else ""
        pre_sign = f"{timestamp}{self.api_key}{self.RECV_WINDOW}{query_string}"
        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            pre_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_headers(self, timestamp: str, params: dict[str, Any]) -> dict[str, Any]:
        signature = self._sign_request(timestamp, params)
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.RECV_WINDOW,
        }

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    @property
    def BASE_URL(self) -> str:  # noqa: N802
        """Domaine retenu par la dernière résolution réussie, sinon le domaine global."""
        return self._base_url or self.BASE_URLS[0]

    async def _resolve_base_url(self) -> str:
        if self._base_url:
            return self._base_url
        for url in self.BASE_URLS:
            try:
                async with self._get_http_client(timeout=10.0) as client:
                    params = {"accountType": "UNIFIED"}
                    timestamp = self._get_timestamp()
                    headers = self._get_headers(timestamp, params)
                    response = await client.get(
                        f"{url}/v5/account/wallet-balance",
                        params=params,
                        headers=headers,
                    )
                    data = response.json()
                    if data.get("retCode") == 0:
                        self._base_url = url
                        logger.info(f"Bybit: resolved base URL to {url}")
                        return url
                    logger.debug(f"Bybit {url}: retCode={data.get('retCode')}, msg={data.get('retMsg')}")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Bybit {url} failed: {e}")
        return self.BASE_URLS[0]

    async def test_connection(self) -> bool:
        """Vrai seulement si l'un des deux domaines a accepté les identifiants."""
        try:
            await self._resolve_base_url()
            return self._base_url is not None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Bybit test_connection error: {e}")
            return False
