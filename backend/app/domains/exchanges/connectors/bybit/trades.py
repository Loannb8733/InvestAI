import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.bybit.core import BybitCore

logger = logging.getLogger(__name__)


class BybitTrades(BybitCore):
    async def get_trades(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Exécutions spot paginées par curseur, sur le domaine courant sans le résoudre."""
        all_trades: list[ExchangeTrade] = []
        try:
            async with self._get_http_client() as client:
                cursor: str | None = None
                fetched = 0

                while fetched < limit:
                    params: dict[str, Any] = {
                        "category": "spot",
                        "limit": str(min(limit - fetched, 100)),
                    }
                    if symbol:
                        params["symbol"] = symbol
                    if start_time:
                        params["startTime"] = str(int(start_time.timestamp() * 1000))
                    if end_time:
                        params["endTime"] = str(int(end_time.timestamp() * 1000))
                    if cursor:
                        params["cursor"] = cursor

                    timestamp = self._get_timestamp()
                    headers = self._get_headers(timestamp, params)
                    response = await client.get(
                        f"{self.BASE_URL}/v5/execution/list",
                        params=params,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data.get("retCode") != 0:
                        logger.error(f"Bybit get_trades error: {data.get('retMsg')}")
                        break

                    result = data.get("result", {})
                    trades_list = result.get("list", [])

                    if not trades_list:
                        break

                    for trade in trades_list:
                        side = trade.get("side", "").lower()
                        exec_time = trade.get("execTime", "0")
                        all_trades.append(
                            ExchangeTrade(
                                trade_id=trade.get("execId", ""),
                                symbol=trade.get("symbol", ""),
                                side=side if side in ("buy", "sell") else "buy",
                                quantity=Decimal(trade.get("execQty", "0")),
                                price=Decimal(trade.get("execPrice", "0")),
                                fee=Decimal(trade.get("execFee", "0")),
                                fee_currency=trade.get("feeCurrency", ""),
                                timestamp=datetime.fromtimestamp(int(exec_time) / 1000, tz=UTC),
                            )
                        )
                        fetched += 1
                        if fetched >= limit:
                            break

                    if fetched >= limit:
                        break
                    next_cursor = result.get("nextPageCursor", "")
                    if not next_cursor:
                        break
                    cursor = next_cursor

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bybit get_trades error: {e}")

        logger.info(f"Bybit: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)
