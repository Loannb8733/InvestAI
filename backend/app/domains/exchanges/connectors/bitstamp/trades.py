import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.bitstamp.core import BitstampCore

logger = logging.getLogger(__name__)


class BitstampTrades(BitstampCore):
    async def get_trades(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Trades extraits des user_transactions de type 2 ; le filtre symbol est ignoré."""
        trades: list[ExchangeTrade] = []
        offset = 0
        page_size = 100

        try:
            while len(trades) < limit:
                transactions = await self._get_user_transactions(offset=offset, limit=page_size)

                if not transactions:
                    break

                for tx in transactions:
                    if len(trades) >= limit:
                        break

                    if int(tx.get("type", -1)) != 2:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    if start_time and tx_datetime < start_time:
                        continue
                    if end_time and tx_datetime > end_time:
                        continue

                    trade_data = self._parse_trade_from_transaction(tx, tx_datetime)
                    if trade_data:
                        trades.append(trade_data)

                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp get_trades error: {e}")

        logger.info(f"Bitstamp: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    def _parse_trade_from_transaction(self, tx: dict[str, Any], tx_datetime: datetime) -> ExchangeTrade | None:
        fiat_currencies = {"usd", "eur", "gbp"}
        bought_currency = None
        bought_amount = Decimal("0")
        sold_currency = None
        sold_amount = Decimal("0")

        for key, value in tx.items():
            if key in ("id", "type", "datetime", "fee", "order_id") or "_" in key:
                continue

            try:
                amount = Decimal(str(value))
            except Exception:  # noqa: BLE001
                continue

            if amount > 0 and key.lower() not in ("id", "type", "fee"):
                bought_currency = key.upper()
                bought_amount = amount
            elif amount < 0:
                sold_currency = key.upper()
                sold_amount = abs(amount)

        if not bought_currency or not sold_currency:
            return None

        if bought_currency.lower() in fiat_currencies:
            side = "sell"
            symbol = f"{sold_currency}_{bought_currency}"
            quantity = sold_amount
            price = bought_amount / sold_amount if sold_amount > 0 else Decimal("0")
        else:
            side = "buy"
            symbol = f"{bought_currency}_{sold_currency}"
            quantity = bought_amount
            price = sold_amount / bought_amount if bought_amount > 0 else Decimal("0")

        fee = Decimal(str(tx.get("fee", "0")))

        return ExchangeTrade(
            trade_id=str(tx.get("id", "")),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            fee=fee,
            fee_currency=sold_currency if side == "buy" else bought_currency,
            timestamp=tx_datetime,
        )
