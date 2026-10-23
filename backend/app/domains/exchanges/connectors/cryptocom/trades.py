import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.cryptocom.core import CryptoComCore

logger = logging.getLogger(__name__)


class CryptoComTrades(CryptoComCore):
    async def _fetch_trades_for_instrument(
        self,
        instrument: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
        semaphore: asyncio.Semaphore,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []

        async with semaphore:
            try:
                params: dict[str, Any] = {"page_size": min(limit, 200), "instrument_name": instrument}

                if start_time:
                    params["start_ts"] = int(start_time.timestamp() * 1000)
                if end_time:
                    params["end_ts"] = int(end_time.timestamp() * 1000)

                result = await self._make_request("private/get-trades", params)

                if result.get("code") != 0:
                    return trades

                trade_list = result.get("result", {}).get("trade_list", [])

                if trade_list:
                    logger.debug(
                        "Crypto.com: Found %d trades for %s",
                        len(trade_list),
                        instrument,
                    )

                for trade in trade_list:
                    instrument_name = trade.get("instrument_name", "")

                    trades.append(
                        ExchangeTrade(
                            trade_id=str(trade["trade_id"]),
                            symbol=instrument_name,
                            side=trade["side"].lower(),
                            quantity=Decimal(str(trade["traded_quantity"])),
                            price=Decimal(str(trade["traded_price"])),
                            fee=Decimal(str(trade.get("fee", 0))),
                            fee_currency=trade.get("fee_currency", "USDT"),
                            timestamp=datetime.fromtimestamp(trade["create_time"] / 1000, tz=UTC),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Crypto.com: failed to fetch trades for %s: %s", instrument, exc)

        return trades

    async def _trade_instruments(self, symbol: str | None) -> set[str]:
        instruments_to_fetch: set[str] = set()

        if symbol:
            for quote in self.QUOTE_CURRENCIES:
                if symbol != quote:
                    instruments_to_fetch.add(f"{symbol}_{quote}")
        else:
            try:
                balances = await self.get_balances()
                logger.debug("Crypto.com: Found %d assets with balance > 0", len(balances))

                for balance in balances:
                    if balance.symbol in self.FIAT_CURRENCIES:
                        continue

                    for quote in self.QUOTE_CURRENCIES:
                        if balance.symbol != quote:
                            instruments_to_fetch.add(f"{balance.symbol}_{quote}")

            except Exception as e:  # noqa: BLE001
                logger.warning("Error fetching balances for trade instruments: %s", e)

        return instruments_to_fetch

    async def get_trades(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Paires du symbole, ou des actifs détenus hors devises, contre cinq quotes, interrogées en parallèle."""
        instruments_to_fetch = await self._trade_instruments(symbol)

        instruments_list = list(instruments_to_fetch)
        logger.debug(
            "Crypto.com: Fetching trades for %d instruments (parallel)",
            len(instruments_list),
        )

        semaphore = asyncio.Semaphore(5)

        tasks = [
            self._fetch_trades_for_instrument(instrument, start_time, end_time, limit, semaphore)
            for instrument in instruments_list
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_trades: list[ExchangeTrade] = []
        for result in results:
            if isinstance(result, list):
                all_trades.extend(result)

        logger.debug("Crypto.com: Total trades found: %d", len(all_trades))
        return sorted(all_trades, key=lambda x: x.timestamp, reverse=True)

    def _conversion_pairs(self, crypto_assets: list[str]) -> set[str]:
        crypto_pairs: set[str] = set()
        for base in crypto_assets:
            for quote in crypto_assets:
                if base != quote:
                    crypto_pairs.add(f"{base}_{quote}")

        common_crypto = ["BTC", "ETH", "CRO", "USDT", "USDC"]
        for base in common_crypto:
            for quote in common_crypto:
                if base != quote and quote not in self.FIAT_CURRENCIES:
                    crypto_pairs.add(f"{base}_{quote}")

        return crypto_pairs

    def _collect_conversions(
        self, results: list[list[ExchangeTrade] | BaseException], conversions: list[ExchangeTrade]
    ) -> None:
        for result in results:
            if isinstance(result, list):
                for trade in result:
                    parts = trade.symbol.split("_")
                    if len(parts) == 2:
                        quote = parts[1]
                        if quote not in self.FIAT_CURRENCIES:
                            conversion_trade = ExchangeTrade(
                                trade_id=f"convert_{trade.trade_id}",
                                symbol=trade.symbol,
                                side=trade.side,
                                quantity=trade.quantity,
                                price=trade.price,
                                fee=trade.fee,
                                fee_currency=trade.fee_currency,
                                timestamp=trade.timestamp,
                            )
                            conversions.append(conversion_trade)

    async def get_crypto_conversions(self, limit: int = 500) -> list[ExchangeTrade]:
        """Trades entre deux cryptos détenues ou courantes, identifiants préfixés « convert_ »."""
        conversions: list[ExchangeTrade] = []

        try:
            balances = await self.get_balances()
            crypto_assets = [b.symbol for b in balances if b.symbol not in self.FIAT_CURRENCIES]

            logger.debug(
                "Crypto.com: Checking %d crypto assets for conversions",
                len(crypto_assets),
            )

            crypto_pairs = self._conversion_pairs(crypto_assets)

            pairs_list = list(crypto_pairs)
            logger.debug("Crypto.com: Checking %d crypto-to-crypto pairs", len(pairs_list))

            semaphore = asyncio.Semaphore(5)

            tasks = [self._fetch_trades_for_instrument(pair, None, None, limit, semaphore) for pair in pairs_list]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            self._collect_conversions(results, conversions)

            logger.debug("Crypto.com: Found %d crypto-to-crypto conversions", len(conversions))

        except Exception as e:  # noqa: BLE001
            logger.warning("Error fetching Crypto.com conversions: %s", e)

        return sorted(conversions, key=lambda x: x.timestamp, reverse=True)
