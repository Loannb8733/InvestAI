import base64
import hashlib
import hmac
import time
from typing import Any

from app.domains.exchanges.connectors.base import BaseExchangeService


class KuCoinCore(BaseExchangeService):
    BASE_URL = "https://api.kucoin.com"

    @property
    def exchange_name(self) -> str:
        return "KuCoin"

    def _get_timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign_request(self, method: str, endpoint: str, body: str = "") -> dict[str, Any]:
        timestamp = self._get_timestamp()
        message = timestamp + method.upper() + endpoint + body

        signature = base64.b64encode(
            hmac.new(
                self._require_secret_key().encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        passphrase = base64.b64encode(
            hmac.new(
                self._require_secret_key().encode("utf-8"),
                (self.passphrase or "").encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }
