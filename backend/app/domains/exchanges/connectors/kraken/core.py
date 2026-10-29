import base64
import hashlib
import hmac
import logging
import re
import time
from decimal import Decimal
from typing import Any, ClassVar
from urllib.parse import urlencode

import httpx

from app.domains.exchanges.connectors.base import BaseExchangeService, ExchangeBalance

logger = logging.getLogger(__name__)

BALANCE_SUFFIXES = ("2.S", ".S", ".M", ".F", ".P", ".B")
BONDED = re.compile(r"([A-Z]{2,})\d{2}")


def _balance_asset(code: str) -> str:
    """Actif d'un code de solde Kraken : suffixe retiré, et durée de blocage d'un staking lié (SOL03.S : SOL)."""
    for suffix in BALANCE_SUFFIXES:
        if code.endswith(suffix):
            stripped = code[: -len(suffix)]
            bonded = BONDED.fullmatch(stripped) if suffix == ".S" else None
            return bonded.group(1) if bonded else stripped
    return code


class KrakenCore(BaseExchangeService):
    BASE_URL = "https://api.kraken.com"

    ASSET_MAP: ClassVar[dict[str, str]] = {
        "XXBT": "BTC",
        "XBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XXLM": "XLM",
        "XXMR": "XMR",
        "XLTC": "LTC",
        "XZEC": "ZEC",
        "XXDG": "DOGE",
        "XDOGE": "DOGE",
        "ZUSD": "USD",
        "ZEUR": "EUR",
        "ZGBP": "GBP",
        "ZJPY": "JPY",
        "ZCAD": "CAD",
        "XSOL": "SOL",
    }

    QUOTE_CURRENCIES: ClassVar[list[str]] = [
        "ZEUR",
        "ZUSD",
        "ZGBP",
        "XXBT",
        "XETH",
        "XBT",
        "EUR",
        "USD",
        "GBP",
        "BTC",
        "ETH",
        "USDT",
        "USDC",
    ]

    FIAT_CURRENCIES: ClassVar[list[str]] = ["EUR", "USD", "GBP", "JPY", "CAD", "AUD", "CHF"]

    @property
    def exchange_name(self) -> str:
        return "Kraken"

    def _normalize_asset(self, asset: str) -> str:
        asset = _balance_asset(asset)
        if asset in self.ASSET_MAP:
            return self.ASSET_MAP[asset]

        if asset.startswith("XX") and len(asset) > 2:
            stripped = asset[2:]
            if stripped in self.ASSET_MAP:
                return self.ASSET_MAP[stripped]
            return stripped

        if asset.startswith("X") and len(asset) > 3:
            stripped = asset[1:]
            if stripped in self.ASSET_MAP:
                return self.ASSET_MAP[stripped]
            if 3 <= len(stripped) <= 5:
                return stripped

        if asset.startswith("Z") and len(asset) == 4:
            return asset[1:]

        return asset

    def _extract_base_from_pair(self, pair: str) -> tuple[str, str]:
        for quote in self.QUOTE_CURRENCIES:
            if pair.endswith(quote):
                base = pair[: -len(quote)]
                normalized_base = self._normalize_asset(base)
                normalized_quote = self._normalize_asset(quote)
                return normalized_base, normalized_quote

        for quote in ["EUR", "USD", "GBP"]:
            zquote = f"Z{quote}"
            if pair.endswith(zquote):
                base = pair[: -len(zquote)]
                return self._normalize_asset(base), quote

        base = pair[:4] if pair.startswith("X") and len(pair) > 6 else pair[:3]

        return self._normalize_asset(base), "EUR"

    def _sign_request(self, uri_path: str, data: dict[str, Any]) -> dict[str, Any]:
        nonce = str(int(time.time() * 1000))
        data["nonce"] = nonce

        post_data = urlencode(data)
        encoded = (nonce + post_data).encode()
        message = uri_path.encode() + hashlib.sha256(encoded).digest()

        signature = hmac.new(
            base64.b64decode(self._require_secret_key()),
            message,
            hashlib.sha512,
        )

        return {
            "API-Key": self.api_key,
            "API-Sign": base64.b64encode(signature.digest()).decode(),
        }

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                uri_path = "/0/private/Balance"
                data: dict[str, Any] = {}
                headers = self._sign_request(uri_path, data)

                response = await client.post(
                    f"{self.BASE_URL}{uri_path}",
                    data=data,
                    headers=headers,
                    timeout=10.0,
                )
                result = response.json()
                errors = result.get("error", [])
                if errors:
                    logger.error(f"Kraken API error: {errors}")
                    return False
                return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Kraken connection test failed: {type(e).__name__}: {e}")
            return False

    async def get_balances(self) -> list[ExchangeBalance]:
        balances: list[ExchangeBalance] = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/Balance"
            data: dict[str, Any] = {}
            headers = self._sign_request(uri_path, data)

            response = await client.post(
                f"{self.BASE_URL}{uri_path}",
                data=data,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("error"):
                raise Exception(str(result["error"]))

            for asset, balance_str in result.get("result", {}).items():
                balance = Decimal(balance_str)
                if balance > 0:
                    normalized_asset = self._normalize_asset(asset)
                    balances.append(
                        ExchangeBalance(
                            symbol=normalized_asset,
                            free=balance,
                            locked=Decimal("0"),
                            total=balance,
                        )
                    )

        return balances
