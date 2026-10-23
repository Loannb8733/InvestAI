import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeFiatOrder
from app.domains.exchanges.connectors.binance.core import BinanceCore, utc_window

logger = logging.getLogger(__name__)


class BinanceFiat(BinanceCore):
    async def get_fiat_orders(  # noqa: C901
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[ExchangeFiatOrder]:
        orders: list[ExchangeFiatOrder] = []

        await self._sync_server_time()

        start_time, end_time = utc_window(start_time, end_time)

        async with self._get_http_client() as client:
            for transaction_type in [0, 1]:
                chunk_end = end_time
                total_orders_for_type = 0

                while chunk_end > start_time:
                    chunk_start = max(chunk_end - timedelta(days=90), start_time)

                    page = 1
                    max_pages = 20

                    while page <= max_pages:
                        try:
                            params: dict[str, Any] = {
                                "transactionType": transaction_type,
                                "beginTime": int(chunk_start.timestamp() * 1000),
                                "endTime": int(chunk_end.timestamp() * 1000),
                                "rows": 500,
                                "page": page,
                            }

                            logger.debug(
                                f"Fiat orders API: type={transaction_type}, page={page}, "
                                f"{chunk_start.date()} to {chunk_end.date()}"
                            )

                            params = self._sign_request(params)
                            response = await self._api_get(
                                client,
                                f"{self.BASE_URL}/sapi/v1/fiat/payments",
                                params=params,
                                headers=self._get_headers(),
                                timeout=30.0,
                            )

                            if response.status_code != 200:
                                logger.error(f"Fiat orders API error: {response.status_code} - {response.text[:200]}")
                                break

                            data = response.json()
                            page_data = data.get("data", [])

                            if not page_data:
                                break

                            logger.debug(
                                f"Fiat orders: found {len(page_data)} orders (type={transaction_type}, page={page})"
                            )
                            if page == 1 and page_data:
                                logger.debug(f"Sample: {page_data[0]}")

                            for order in page_data:
                                if order.get("status") != "Completed":
                                    continue

                                side = "buy" if transaction_type == 0 else "sell"
                                crypto_amount = Decimal(str(order.get("obtainAmount", 0)))
                                fiat_amount = Decimal(str(order.get("sourceAmount", 0)))

                                if side == "sell":
                                    crypto_amount = Decimal(str(order.get("sourceAmount", 0)))
                                    fiat_amount = Decimal(str(order.get("obtainAmount", 0)))

                                price = fiat_amount / crypto_amount if crypto_amount > 0 else Decimal("0")

                                orders.append(
                                    ExchangeFiatOrder(
                                        order_id=order.get("orderNo", str(order.get("createTime", ""))),
                                        crypto_symbol=order.get("cryptoCurrency", ""),
                                        fiat_currency=order.get("fiatCurrency", "EUR"),
                                        side=side,
                                        crypto_amount=crypto_amount,
                                        fiat_amount=fiat_amount,
                                        price=price,
                                        fee=Decimal(str(order.get("totalFee", 0))),
                                        status=order.get("status", "unknown"),
                                        timestamp=datetime.fromtimestamp(order.get("createTime", 0) / 1000, tz=UTC),
                                    )
                                )
                                total_orders_for_type += 1

                            if len(page_data) < 500:
                                break

                            page += 1

                        except Exception as e:  # noqa: BLE001
                            logger.error(f"Error fetching fiat orders: {e}")
                            break

                    chunk_end = chunk_start - timedelta(seconds=1)

                logger.info(f"Total fiat orders for type {transaction_type}: {total_orders_for_type}")

        logger.info(f"Total fiat orders found: {len(orders)}")
        return sorted(orders, key=lambda x: x.timestamp, reverse=True)

    async def get_convert_history(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[ExchangeFiatOrder]:
        """Conversions fiat <-> crypto, depuis le lancement de Binance par défaut, en fenêtres de 30 jours."""
        start, window_end = utc_window(start_time, end_time)
        orders: list[ExchangeFiatOrder] = []
        while window_end > start:
            window_start = max(window_end - timedelta(days=30), start)
            orders.extend(await self._convert_window(window_start, window_end, limit))
            window_end = window_start - timedelta(seconds=1)
        return orders

    async def _convert_window(  # noqa: C901
        self,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[ExchangeFiatOrder]:
        orders: list[ExchangeFiatOrder] = []

        await self._sync_server_time()

        async with self._get_http_client() as client:
            try:
                page_size = min(limit, 1000)
                all_conversions: list[dict[str, Any]] = []

                while len(all_conversions) < limit:
                    params: dict[str, Any] = {
                        "limit": page_size,
                    }

                    if start_time:
                        params["startTime"] = int(start_time.timestamp() * 1000)
                    if end_time:
                        params["endTime"] = int(end_time.timestamp() * 1000)

                    params = self._sign_request(params)
                    response = await self._api_get(
                        client,
                        f"{self.BASE_URL}/sapi/v1/convert/tradeFlow",
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        logger.error(f"Convert history API error: {response.status_code} - {response.text[:200]}")
                        break

                    data = response.json()
                    convert_list = data.get("list", [])

                    if not convert_list:
                        break

                    all_conversions.extend(convert_list)

                    if len(convert_list) < page_size:
                        break

                    oldest_time = min(c.get("createTime", 0) for c in convert_list)
                    end_time = datetime.fromtimestamp((oldest_time - 1) / 1000, tz=UTC)

                if all_conversions:
                    logger.info(f"Convert history: {len(all_conversions)} conversions found")

                for conv in all_conversions:
                    from_asset = conv.get("fromAsset", "")
                    to_asset = conv.get("toAsset", "")
                    from_amount = Decimal(str(conv.get("fromAmount", 0)))
                    to_amount = Decimal(str(conv.get("toAmount", 0)))

                    fiat_currencies = ["EUR", "USD", "GBP", "TRY", "RUB", "UAH", "BRL"]

                    if from_asset in fiat_currencies and to_asset not in fiat_currencies:
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=str(conv.get("quoteId", conv.get("orderId", ""))),
                                crypto_symbol=to_asset,
                                fiat_currency=from_asset,
                                side="buy",
                                crypto_amount=to_amount,
                                fiat_amount=from_amount,
                                price=from_amount / to_amount if to_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000, tz=UTC),
                            )
                        )
                    elif from_asset not in fiat_currencies and to_asset in fiat_currencies:
                        orders.append(
                            ExchangeFiatOrder(
                                order_id=str(conv.get("quoteId", conv.get("orderId", ""))),
                                crypto_symbol=from_asset,
                                fiat_currency=to_asset,
                                side="sell",
                                crypto_amount=from_amount,
                                fiat_amount=to_amount,
                                price=to_amount / from_amount if from_amount > 0 else Decimal("0"),
                                fee=Decimal("0"),
                                status="Completed",
                                timestamp=datetime.fromtimestamp(conv.get("createTime", 0) / 1000, tz=UTC),
                            )
                        )

            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching convert history: {e}")

        return orders
