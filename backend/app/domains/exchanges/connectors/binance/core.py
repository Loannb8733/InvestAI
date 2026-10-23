import asyncio
import hashlib
import hmac
import logging
import ssl
import time
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urlencode

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

BINANCE_LAUNCH = datetime(2017, 7, 1, tzinfo=UTC)


def utc_window(start_time: datetime | None, end_time: datetime | None) -> tuple[datetime, datetime]:
    """Fenêtre en UTC, du lancement de Binance à maintenant par défaut ; une date naïve est lue en UTC."""
    start = start_time or BINANCE_LAUNCH
    end = end_time or datetime.now(UTC)
    return (
        start if start.tzinfo else start.replace(tzinfo=UTC),
        end if end.tzinfo else end.replace(tzinfo=UTC),
    )


logger = logging.getLogger(__name__)


class BinanceCore(BaseExchangeService):
    BASE_URL = "https://api.binance.com"
    QUOTE_CURRENCIES: ClassVar[list[str]] = ["USDT", "EUR", "USDC", "BTC", "FDUSD"]
    FIAT_CURRENCIES: ClassVar[list[str]] = ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL", "AUD", "CAD"]

    _REQUEST_INTERVAL = 0.3

    def __init__(self, api_key: str, secret_key: str | None, passphrase: str | None = None) -> None:
        super().__init__(api_key, secret_key, passphrase)
        self._server_time_offset: int = 0
        self._all_account_symbols: set[str] = set()
        self._valid_pairs: set[str] = set()
        self._last_request_time: float = 0

    @property
    def exchange_name(self) -> str:
        return "Binance"

    def _get_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_default_certs()
        return context

    def _get_http_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=self._get_ssl_context(),
            timeout=timeout,
        )

    async def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._REQUEST_INTERVAL:
            await asyncio.sleep(self._REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    async def _api_get(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        await self._throttle()
        return await client.get(url, **kwargs)

    async def _api_post(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        await self._throttle()
        return await client.post(url, **kwargs)

    async def _sync_server_time(self) -> None:
        try:
            async with self._get_http_client(timeout=10.0) as client:
                response = await self._api_get(
                    client,
                    f"{self.BASE_URL}/api/v3/time",
                )
                if response.status_code == 200:
                    server_time = response.json().get("serverTime", 0)
                    local_time = int(time.time() * 1000)
                    self._server_time_offset = server_time - local_time
                    logger.debug(f"Binance time sync: offset = {self._server_time_offset}ms")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to sync Binance server time: {e}")
            self._server_time_offset = 0

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000) + self._server_time_offset

    def _sign_request(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = self._get_timestamp()
        params["recvWindow"] = 60000
        query_string = urlencode(params)
        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _get_headers(self) -> dict[str, Any]:
        return {"X-MBX-APIKEY": self.api_key}

    async def connection_error(self) -> str | None:
        """Message renvoyé par /api/v3/account, ou None s'il répond ou ne répond pas du tout."""
        try:
            async with self._get_http_client(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/v3/account", params=self._sign_request({}), headers=self._get_headers()
                )
            if response.status_code == 200:
                return None
            return f"HTTP {response.status_code}: {response.json().get('msg', response.text[:200])}"
        except Exception:  # noqa: BLE001
            return None

    async def test_connection(self) -> bool:
        try:
            await self._sync_server_time()

            async with self._get_http_client(timeout=15.0) as client:
                params = self._sign_request({})
                response = await self._api_get(
                    client,
                    f"{self.BASE_URL}/api/v3/account",
                    params=params,
                    headers=self._get_headers(),
                )
                if response.status_code != 200:
                    logger.error(f"Binance test_connection failed: HTTP {response.status_code} — {response.text}")
                return response.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.error(f"Binance test_connection error: {e}")
            return False
