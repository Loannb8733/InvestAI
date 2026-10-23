import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.binance.core import BinanceCore, utc_window

logger = logging.getLogger(__name__)


class BinanceConversions(BinanceCore):
    async def get_crypto_conversions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeTrade]:
        """Conversions Convert hors devise, chacune rendue en deux jambes : vente puis achat."""
        conversions: list[ExchangeTrade] = []

        fiat_currencies = [
            "EUR",
            "USD",
            "GBP",
            "TRY",
            "RUB",
            "UAH",
            "BRL",
            "AUD",
            "CAD",
        ]
        stablecoins = ["USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD"]

        await self._sync_server_time()

        start_time, end_time = utc_window(start_time, end_time)

        chunk_end = end_time

        async with self._get_http_client() as client:
            while chunk_end > start_time:
                chunk_start = max(chunk_end - timedelta(days=30), start_time)

                try:
                    params: dict[str, Any] = {
                        "limit": min(limit, 1000),
                        "startTime": int(chunk_start.timestamp() * 1000),
                        "endTime": int(chunk_end.timestamp() * 1000),
                    }

                    params = self._sign_request(params)
                    response = await self._api_get(
                        client,
                        f"{self.BASE_URL}/sapi/v1/convert/tradeFlow",
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        chunk_end = chunk_start - timedelta(seconds=1)
                        continue

                    data = response.json()
                    convert_list = data.get("list", [])

                    for conv in convert_list:
                        from_asset = conv.get("fromAsset", "")
                        to_asset = conv.get("toAsset", "")
                        from_amount = Decimal(str(conv.get("fromAmount", 0)))
                        to_amount = Decimal(str(conv.get("toAmount", 0)))
                        order_id = str(conv.get("quoteId", conv.get("orderId", "")))
                        timestamp = datetime.fromtimestamp(conv.get("createTime", 0) / 1000, tz=UTC)

                        if from_asset in fiat_currencies:
                            continue

                        rate = to_amount / from_amount if from_amount > 0 else Decimal("0")

                        if to_asset in fiat_currencies:
                            continue
                        elif to_asset in stablecoins:
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            logger.debug(f"Binance: Found conversion {from_asset} -> {to_asset} (to stablecoin)")
                        elif from_asset in stablecoins:
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            logger.debug(f"Binance: Found conversion {from_asset} -> {to_asset} (from stablecoin)")
                        else:
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_sell_{order_id}",
                                    symbol=f"{from_asset}{to_asset}",
                                    side="sell",
                                    quantity=from_amount,
                                    price=rate,
                                    fee=Decimal("0"),
                                    fee_currency=from_asset,
                                    timestamp=timestamp,
                                )
                            )
                            conversions.append(
                                ExchangeTrade(
                                    trade_id=f"convert_buy_{order_id}",
                                    symbol=f"{to_asset}{from_asset}",
                                    side="buy",
                                    quantity=to_amount,
                                    price=Decimal("1") / rate if rate > 0 else Decimal("0"),
                                    fee=Decimal("0"),
                                    fee_currency=to_asset,
                                    timestamp=timestamp,
                                )
                            )
                            logger.debug(f"Binance: Found conversion {from_asset} -> {to_asset}")

                except Exception as e:  # noqa: BLE001
                    logger.error(f"Error fetching Binance conversions: {e}")

                chunk_end = chunk_start - timedelta(seconds=1)

        logger.info(f"Binance: Total crypto conversions found: {len(conversions) // 2}")
        return sorted(conversions, key=lambda x: x.timestamp, reverse=True)
