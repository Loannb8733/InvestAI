import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.kucoin.core import KuCoinCore

logger = logging.getLogger(__name__)


class KuCoinTrades(KuCoinCore):
    async def get_trades(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []

        try:
            current_page = 1
            page_size = min(limit, 500)

            async with httpx.AsyncClient() as client:
                while len(trades) < limit:
                    endpoint = f"/api/v1/fills?currentPage={current_page}&pageSize={page_size}"

                    if symbol:
                        endpoint += f"&symbol={symbol}"
                    if start_time:
                        endpoint += f"&startAt={int(start_time.timestamp() * 1000)}"
                    if end_time:
                        endpoint += f"&endAt={int(end_time.timestamp() * 1000)}"

                    headers = self._sign_request("GET", endpoint)

                    response = await client.get(
                        f"{self.BASE_URL}{endpoint}",
                        headers=headers,
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"KuCoin get_trades error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()

                    if data.get("code") != "200000":
                        logger.error(f"KuCoin get_trades API error: {data.get('msg', 'Unknown error')}")
                        break

                    items = data.get("data", {}).get("items", [])

                    if not items:
                        break

                    for fill in items:
                        if len(trades) >= limit:
                            break

                        trade_symbol = fill.get("symbol", "")
                        fee_currency = fill.get("feeCurrency", "")

                        trades.append(
                            ExchangeTrade(
                                trade_id=fill.get("tradeId", ""),
                                symbol=trade_symbol,
                                side=fill.get("side", "").lower(),
                                quantity=Decimal(fill.get("size", "0")),
                                price=Decimal(fill.get("price", "0")),
                                fee=Decimal(fill.get("fee", "0")),
                                fee_currency=fee_currency,
                                timestamp=datetime.fromtimestamp(int(fill.get("createdAt", 0)) / 1000, tz=UTC),
                            )
                        )

                    total_pages = data.get("data", {}).get("totalPage", 1)
                    if current_page >= total_pages:
                        break

                    current_page += 1

        except Exception as e:  # noqa: BLE001
            logger.error(f"KuCoin get_trades error: {e}")

        logger.info(f"KuCoin: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)
