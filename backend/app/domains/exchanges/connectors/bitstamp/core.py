import hashlib
import hmac
import logging
import time
import uuid
from typing import Any, ClassVar

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService

logger = logging.getLogger(__name__)


class BitstampCore(BaseExchangeService):
    BASE_URL = "https://www.bitstamp.net"

    KNOWN_CURRENCIES: ClassVar[list[str]] = [
        "btc",
        "eth",
        "xrp",
        "ltc",
        "bch",
        "xlm",
        "link",
        "omg",
        "usdc",
        "pax",
        "gbp",
        "eur",
        "usd",
        "sol",
        "ada",
        "dot",
        "matic",
        "avax",
        "doge",
        "shib",
        "uni",
        "aave",
        "algo",
        "atom",
        "near",
        "ape",
        "sand",
        "mana",
        "axs",
        "grt",
        "mkr",
        "snx",
        "comp",
        "crv",
        "sushi",
        "yfi",
        "bat",
        "enj",
        "storj",
        "skl",
        "ftm",
        "imx",
        "op",
        "arb",
        "pepe",
        "floki",
        "sui",
        "apt",
        "rndr",
        "inj",
        "fet",
    ]

    @property
    def exchange_name(self) -> str:
        return "Bitstamp"

    def _generate_auth_headers(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
        content_type: str = "",
    ) -> dict[str, Any]:
        nonce = str(uuid.uuid4())
        timestamp = str(int(time.time() * 1000))
        host = "www.bitstamp.net"

        x_auth = f"BITSTAMP {self.api_key}"

        message = x_auth + method.upper() + host + path + query + content_type + nonce + timestamp + "v2" + body

        signature = hmac.new(
            self._require_secret_key().encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-Auth": x_auth,
            "X-Auth-Signature": signature,
            "X-Auth-Nonce": nonce,
            "X-Auth-Timestamp": timestamp,
            "X-Auth-Version": "v2",
        }

    async def _get_user_transactions(
        self,
        offset: int = 0,
        limit: int = 100,
        sort: str = "desc",
    ) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/user_transactions/"
                body = f"offset={offset}&limit={limit}&sort={sort}"
                content_type = "application/x-www-form-urlencoded"

                headers = self._generate_auth_headers("POST", path, body=body, content_type=content_type)
                headers["Content-Type"] = content_type

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    content=body,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Bitstamp user_transactions error: {response.status_code} - {response.text[:200]}")
                    return []

                transactions: list[dict[str, Any]] = response.json()
                return transactions

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp _get_user_transactions error: {e}")
            return []
