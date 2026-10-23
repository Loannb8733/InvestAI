import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.binance.core import BinanceCore

logger = logging.getLogger(__name__)


class BinanceTrades(BinanceCore):
    async def _get_all_account_symbols(self) -> set[str]:
        if self._all_account_symbols:
            return self._all_account_symbols

        await self._sync_server_time()

        async with self._get_http_client(timeout=30.0) as client:
            params = self._sign_request({})
            response = await self._api_get(
                client,
                f"{self.BASE_URL}/api/v3/account",
                params=params,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()

            for asset in data.get("balances", []):
                self._all_account_symbols.add(asset["asset"])

        return self._all_account_symbols

    async def _get_valid_trading_pairs(self) -> set[str]:
        if self._valid_pairs:
            return self._valid_pairs

        try:
            async with self._get_http_client(timeout=30.0) as client:
                response = await self._api_get(
                    client,
                    f"{self.BASE_URL}/api/v3/exchangeInfo",
                )
                if response.status_code == 200:
                    data = response.json()
                    self._valid_pairs = {
                        symbol["symbol"] for symbol in data.get("symbols", []) if symbol.get("status") == "TRADING"
                    }
                    logger.info(f"Binance: {len(self._valid_pairs)} valid trading pairs cached")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error fetching exchange info: {e}")

        return self._valid_pairs

    async def _fetch_trades_for_symbol(  # noqa: C901
        self,
        client: httpx.AsyncClient,
        trading_symbol: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
        semaphore: asyncio.Semaphore,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []

        async with semaphore:
            try:
                from_id: int | None = None
                page_limit = min(limit, 1000)

                while True:
                    params: dict[str, Any] = {"symbol": trading_symbol, "limit": page_limit}

                    if from_id:
                        params["fromId"] = from_id
                    elif start_time:
                        params["startTime"] = int(start_time.timestamp() * 1000)

                    if end_time and not from_id:
                        params["endTime"] = int(end_time.timestamp() * 1000)

                    params = self._sign_request(params)
                    response = await self._api_get(
                        client,
                        f"{self.BASE_URL}/api/v3/myTrades",
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        break

                    data = response.json()
                    if not data:
                        break

                    logger.debug(f"Binance: Found {len(data)} trades for {trading_symbol} (page)")

                    for trade in data:
                        side = "buy" if trade["isBuyer"] else "sell"
                        trades.append(
                            ExchangeTrade(
                                trade_id=str(trade["id"]),
                                symbol=trading_symbol,
                                side=side,
                                quantity=Decimal(trade["qty"]),
                                price=Decimal(trade["price"]),
                                fee=Decimal(trade["commission"]),
                                fee_currency=trade["commissionAsset"],
                                timestamp=datetime.fromtimestamp(trade["time"] / 1000, tz=UTC),
                            )
                        )

                    if len(data) < page_limit:
                        break

                    if len(trades) >= limit:
                        break

                    from_id = data[-1]["id"] + 1

            except Exception as e:  # noqa: BLE001
                logger.warning(f"Error fetching trades for {trading_symbol}: {e}")

        return trades

    async def get_trades(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        await self._sync_server_time()

        valid_pairs = await self._get_valid_trading_pairs()

        symbols_to_fetch: set[str] = set()

        if symbol:
            for quote in self.QUOTE_CURRENCIES:
                pair = f"{symbol}{quote}"
                if pair in valid_pairs:
                    symbols_to_fetch.add(pair)
        else:
            try:
                all_symbols = await self._get_all_account_symbols()
                logger.info(f"Binance: Account has {len(all_symbols)} symbols (including 0 balance)")

                for asset_symbol in all_symbols:
                    if asset_symbol in self.FIAT_CURRENCIES:
                        continue
                    for quote in self.QUOTE_CURRENCIES:
                        if asset_symbol != quote:
                            pair = f"{asset_symbol}{quote}"
                            if pair in valid_pairs:
                                symbols_to_fetch.add(pair)

            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching account symbols for trade pairs: {e}")

        symbols_list = list(symbols_to_fetch)
        logger.info(f"Binance: Fetching trades for {len(symbols_list)} valid trading pairs (parallel)...")

        semaphore = asyncio.Semaphore(10)

        async with self._get_http_client() as client:
            tasks = [
                self._fetch_trades_for_symbol(client, trading_symbol, start_time, end_time, limit, semaphore)
                for trading_symbol in symbols_list
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_trades: list[ExchangeTrade] = []
        for result in results:
            if isinstance(result, list):
                all_trades.extend(result)

        logger.info(f"Binance: Total trades found: {len(all_trades)}")
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)
