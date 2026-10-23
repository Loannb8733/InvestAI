import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.gateio.core import GateIOCore

logger = logging.getLogger(__name__)


class GateIOTrades(GateIOCore):
    async def get_trades(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Sans symbole, interroge les paires formées à partir des soldes courants."""
        trades: list[ExchangeTrade] = []

        try:
            if symbol:
                pairs = [symbol]
            else:
                pairs = await self._get_trading_pairs_from_balances()

            async with httpx.AsyncClient() as client:
                for pair in pairs:
                    pair_trades = await self._fetch_trades_for_pair(
                        client, pair, start_time, end_time, limit - len(trades)
                    )
                    trades.extend(pair_trades)

                    if len(trades) >= limit:
                        break

        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io get_trades error: {e}")

        logger.info(f"Gate.io: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)[:limit]

    async def _get_trading_pairs_from_balances(self) -> list[str]:
        pairs: list[str] = []
        quote_currencies = ["USDT", "USD", "BTC", "ETH"]
        fiat_currencies = {"USD", "EUR", "GBP", "USDT", "USDC"}

        try:
            balances = await self.get_balances()
            for balance in balances:
                if balance.symbol in fiat_currencies:
                    continue
                for quote in quote_currencies:
                    if balance.symbol != quote:
                        pairs.append(f"{balance.symbol}_{quote}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate.io error building trading pairs: {e}")

        return pairs

    async def _fetch_trades_for_pair(
        self,
        client: httpx.AsyncClient,
        currency_pair: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []
        page = 1
        page_size = min(limit, 100)

        while len(trades) < limit:
            try:
                path = "/api/v4/spot/my_trades"
                query_params = {
                    "currency_pair": currency_pair,
                    "limit": str(page_size),
                    "page": str(page),
                }

                if start_time:
                    query_params["from"] = str(int(start_time.timestamp()))
                if end_time:
                    query_params["to"] = str(int(end_time.timestamp()))

                query_string = "&".join(f"{k}={v}" for k, v in sorted(query_params.items()))
                headers = self._sign_request("GET", path, query=query_string)

                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    params=query_params,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    break

                data = response.json()

                if not data:
                    break

                for trade in data:
                    if len(trades) >= limit:
                        break

                    trades.append(
                        ExchangeTrade(
                            trade_id=str(trade.get("id", "")),
                            symbol=trade.get("currency_pair", currency_pair),
                            side=trade.get("side", "").lower(),
                            quantity=Decimal(str(trade.get("amount", "0"))),
                            price=Decimal(str(trade.get("price", "0"))),
                            fee=Decimal(str(trade.get("fee", "0"))),
                            fee_currency=trade.get("fee_currency", ""),
                            timestamp=datetime.fromtimestamp(int(trade.get("create_time", 0)), tz=UTC),
                        )
                    )

                if len(data) < page_size:
                    break

                page += 1

            except Exception as e:  # noqa: BLE001
                logger.error(f"Gate.io error fetching trades for {currency_pair}: {e}")
                break

        return trades
