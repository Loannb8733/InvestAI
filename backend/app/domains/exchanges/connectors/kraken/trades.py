from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeTrade, ExchangeWithdrawal
from app.domains.exchanges.connectors.kraken.core import KrakenCore


class KrakenTrades(KrakenCore):
    async def get_trades(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 10000,
    ) -> list[ExchangeTrade]:
        trades: list[ExchangeTrade] = []
        offset = 0

        async with httpx.AsyncClient() as client:
            while len(trades) < limit:
                uri_path = "/0/private/TradesHistory"
                data = {"ofs": offset}

                if start_time:
                    data["start"] = int(start_time.timestamp())
                if end_time:
                    data["end"] = int(end_time.timestamp())

                headers = self._sign_request(uri_path, data)

                response = await client.post(
                    f"{self.BASE_URL}{uri_path}",
                    data=data,
                    headers=headers,
                    timeout=30.0,
                )
                result = response.json()

                if result.get("error"):
                    break

                trades_data = result.get("result", {}).get("trades", {})

                if not trades_data:
                    break

                for trade_id, trade in trades_data.items():
                    if len(trades) >= limit:
                        break

                    pair = trade["pair"]
                    base_asset, quote_currency = self._extract_base_from_pair(pair)

                    normalized_symbol = f"{base_asset}{quote_currency}"

                    trades.append(
                        ExchangeTrade(
                            trade_id=trade_id,
                            symbol=normalized_symbol,
                            side=trade["type"],
                            quantity=Decimal(trade["vol"]),
                            price=Decimal(trade["price"]),
                            fee=Decimal(trade["fee"]),
                            fee_currency=quote_currency,
                            timestamp=datetime.fromtimestamp(trade["time"], tz=UTC),
                        )
                    )

                offset += len(trades_data)

                if len(trades_data) < 50:
                    break

        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        deposits: list[ExchangeDeposit] = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/DepositStatus"
            data: dict[str, Any] = {}

            if symbol:
                data["asset"] = symbol

            headers = self._sign_request(uri_path, data)

            response = await client.post(
                f"{self.BASE_URL}{uri_path}",
                data=data,
                headers=headers,
                timeout=30.0,
            )
            result = response.json()

            if result.get("error"):
                return deposits

            for deposit in result.get("result", [])[:limit]:
                deposits.append(
                    ExchangeDeposit(
                        deposit_id=deposit.get("refid", ""),
                        symbol=self._normalize_asset(deposit["asset"]),
                        amount=Decimal(deposit["amount"]),
                        timestamp=datetime.fromtimestamp(deposit["time"], tz=UTC),
                        status=deposit["status"],
                        tx_id=deposit.get("txid"),
                    )
                )

        return deposits

    async def get_withdrawals(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        withdrawals: list[ExchangeWithdrawal] = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/WithdrawStatus"
            data: dict[str, Any] = {}

            if symbol:
                data["asset"] = symbol

            headers = self._sign_request(uri_path, data)

            response = await client.post(
                f"{self.BASE_URL}{uri_path}",
                data=data,
                headers=headers,
                timeout=30.0,
            )
            result = response.json()

            if result.get("error"):
                return withdrawals

            for withdrawal in result.get("result", [])[:limit]:
                withdrawals.append(
                    ExchangeWithdrawal(
                        withdrawal_id=withdrawal.get("refid", ""),
                        symbol=self._normalize_asset(withdrawal["asset"]),
                        amount=Decimal(withdrawal["amount"]),
                        fee=Decimal(withdrawal.get("fee", 0)),
                        timestamp=datetime.fromtimestamp(withdrawal["time"], tz=UTC),
                        status=withdrawal["status"],
                        tx_id=withdrawal.get("txid"),
                    )
                )

        return withdrawals
