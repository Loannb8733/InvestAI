import logging
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.bybit.core import BybitCore

logger = logging.getLogger(__name__)


class BybitBalances(BybitCore):
    async def get_balances(self) -> list[ExchangeBalance]:
        balances: list[ExchangeBalance] = []
        try:
            base_url = await self._resolve_base_url()
            async with self._get_http_client() as client:
                params = {"accountType": "UNIFIED"}
                timestamp = self._get_timestamp()
                headers = self._get_headers(timestamp, params)
                response = await client.get(
                    f"{base_url}/v5/account/wallet-balance",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("retCode") != 0:
                    logger.error(f"Bybit get_balances error: {data.get('retMsg')}")
                    return balances

                result = data.get("result", {})
                accounts = result.get("list", [])

                for account in accounts:
                    for coin in account.get("coin", []):
                        free = Decimal(coin.get("availableToWithdraw", "0"))
                        locked = Decimal(coin.get("locked", "0"))
                        total = Decimal(coin.get("walletBalance", "0"))

                        if total > 0:
                            balances.append(
                                ExchangeBalance(
                                    symbol=coin.get("coin", ""),
                                    free=free,
                                    locked=locked,
                                    total=total,
                                )
                            )

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bybit get_balances error: {e}")

        return balances
