import logging
from datetime import datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.coinbase.core import CoinbaseCore

logger = logging.getLogger(__name__)


class CoinbaseTrades(CoinbaseCore):
    async def get_trades(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []

        try:
            cursor: str | None = None
            fetched = 0

            async with httpx.AsyncClient() as client:
                while fetched < limit:
                    page_size = min(limit - fetched, 100)
                    request_path = f"/api/v3/brokerage/orders/historical/fills?limit={page_size}"

                    if symbol:
                        request_path += f"&product_id={symbol}"
                    if start_time:
                        request_path += f"&start_sequence_timestamp={start_time.isoformat()}Z"
                    if end_time:
                        request_path += f"&end_sequence_timestamp={end_time.isoformat()}Z"
                    if cursor:
                        request_path += f"&cursor={cursor}"

                    headers = self._sign_request("GET", request_path)

                    response = await client.get(
                        f"{self.BASE_URL}{request_path}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"Coinbase get_trades error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()
                    fills = data.get("fills", [])

                    if not fills:
                        break

                    for fill in fills:
                        product_id = fill.get("product_id", "")

                        trades.append(
                            ExchangeTrade(
                                trade_id=fill.get("trade_id", fill.get("entry_id", "")),
                                symbol=product_id,
                                side=fill.get("side", "").lower(),
                                quantity=Decimal(fill.get("size", "0")),
                                price=Decimal(fill.get("price", "0")),
                                fee=Decimal(fill.get("commission", "0")),
                                fee_currency=product_id.split("-")[-1] if "-" in product_id else "USD",
                                timestamp=datetime.fromisoformat(fill.get("trade_time", "").replace("Z", "+00:00")),
                            )
                        )

                    fetched += len(fills)

                    cursor = data.get("cursor")
                    if not cursor:
                        break

        except Exception as e:  # noqa: BLE001
            logger.error(f"Coinbase get_trades error: {e}")

        logger.info(f"Coinbase: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)
