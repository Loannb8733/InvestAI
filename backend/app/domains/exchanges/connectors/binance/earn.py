import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeFiatOrder, ExchangeTrade
from app.domains.exchanges.connectors.binance.core import BinanceCore

logger = logging.getLogger(__name__)


class BinanceEarn(BinanceCore):
    async def get_auto_invest_history(  # noqa: C901
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 5000,
    ) -> list[ExchangeFiatOrder]:
        """Achats Auto-Invest réussis, par pages de 100."""
        orders: list[ExchangeFiatOrder] = []

        async with self._get_http_client() as client:
            page = 1
            max_pages = 50

            while page <= max_pages and len(orders) < limit:
                try:
                    params: dict[str, Any] = {
                        "size": 100,
                        "current": page,
                    }

                    if start_time:
                        params["startTime"] = int(start_time.timestamp() * 1000)
                    if end_time:
                        params["endTime"] = int(end_time.timestamp() * 1000)

                    params = self._sign_request(params)
                    response = await self._api_get(
                        client,
                        f"{self.BASE_URL}/sapi/v1/lending/auto-invest/history/list",
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )

                    if response.status_code != 200:
                        break

                    data = response.json()
                    invest_list = data.get("list", [])

                    if not invest_list:
                        break

                    if page == 1:
                        logger.info(f"Auto-invest history: fetching page {page}...")

                    for invest in invest_list:
                        if invest.get("transactionStatus", invest.get("status")) != "SUCCESS":
                            continue

                        target_asset = invest.get("targetAsset", "")
                        source_asset = invest.get("sourceAsset", "EUR")
                        executed_amount = Decimal(str(invest.get("targetAssetAmount", invest.get("executedAmount", 0))))
                        moment = invest.get("transactionDateTime", invest.get("transactionTime", 0))
                        fee = Decimal(str(invest.get("transactionFee", 0)))
                        if invest.get("transactionFeeUnit", source_asset) != source_asset:
                            fee = Decimal("0")
                        source_amount = Decimal(str(invest.get("sourceAssetAmount", 0)))

                        if executed_amount > 0:
                            orders.append(
                                ExchangeFiatOrder(
                                    order_id=f"autoinvest_{invest.get('id', moment)}",
                                    crypto_symbol=target_asset,
                                    fiat_currency=source_asset,
                                    side="buy",
                                    crypto_amount=executed_amount,
                                    fiat_amount=source_amount,
                                    price=source_amount / executed_amount if executed_amount > 0 else Decimal("0"),
                                    fee=fee,
                                    status="Completed",
                                    timestamp=datetime.fromtimestamp(int(moment) / 1000, tz=UTC),
                                )
                            )

                    if len(invest_list) < 100:
                        break

                    page += 1

                except Exception as e:  # noqa: BLE001
                    logger.error(f"Error fetching auto-invest history: {e}")
                    break

        if orders:
            logger.info(f"Auto-invest history: {len(orders)} orders found total")

        return orders

    async def get_rewards(  # noqa: C901
        self, limit: int = 500, lookback_days: int = 730, **kwargs: Any
    ) -> list[ExchangeTrade]:
        """Intérêts Simple Earn sur lookback_days, en fenêtres de 29 jours dédoublonnées ; limit est ignoré."""
        trades: list[ExchangeTrade] = []

        await self._sync_server_time()

        now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        window_ms = 29 * 24 * 60 * 60 * 1000
        oldest_ms = now_ms - lookback_days * 24 * 60 * 60 * 1000

        windows: list[tuple[int, int]] = []
        cursor = now_ms
        while cursor > oldest_ms:
            start = max(cursor - window_ms, oldest_ms)
            windows.append((start, cursor))
            cursor = start

        async with self._get_http_client(timeout=30.0) as client:
            earn_queries = [
                ("/sapi/v1/simple-earn/flexible/history/rewardsRecord", "BONUS"),
                ("/sapi/v1/simple-earn/flexible/history/rewardsRecord", "REALTIME"),
                ("/sapi/v1/simple-earn/locked/history/rewardsRecord", "BONUS"),
                ("/sapi/v1/simple-earn/locked/history/rewardsRecord", "REALTIME"),
                ("/sapi/v1/simple-earn/locked/history/rewardsRecord", "REWARDS"),
            ]
            for endpoint, reward_type in earn_queries:
                for win_start, win_end in windows:
                    try:
                        current = 1
                        while True:
                            params = self._sign_request(
                                {
                                    "type": reward_type,
                                    "current": current,
                                    "size": 100,
                                    "startTime": win_start,
                                    "endTime": win_end,
                                }
                            )
                            response = await self._api_get(
                                client,
                                f"{self.BASE_URL}{endpoint}",
                                params=params,
                                headers=self._get_headers(),
                            )
                            if response.status_code != 200:
                                logger.warning(
                                    f"Earn rewards {endpoint} type={reward_type} "
                                    f"window={win_start}-{win_end}: HTTP {response.status_code} — {response.text}"
                                )
                                break
                            data = response.json()
                            rows = data.get("rows", [])
                            if not rows:
                                break
                            for row in rows:
                                asset = row.get("asset", "")
                                rewards_amt = Decimal(str(row.get("rewards", "0")))
                                if rewards_amt <= 0 or not asset:
                                    continue
                                raw_time = row.get("time", 0)
                                ts = datetime.fromtimestamp(raw_time / 1000, tz=UTC)
                                trades.append(
                                    ExchangeTrade(
                                        trade_id=f"reward_staking_{asset}_{reward_type}_{raw_time}",
                                        symbol=f"{asset}EUR",
                                        side="buy",
                                        quantity=rewards_amt,
                                        price=Decimal("0"),
                                        fee=Decimal("0"),
                                        fee_currency="EUR",
                                        timestamp=ts,
                                    )
                                )
                            total_records = data.get("total", 0)
                            if current * 100 >= total_records:
                                break
                            current += 1
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"Failed to fetch {endpoint} type={reward_type} window={win_start}-{win_end}: {e}"
                        )

        seen: set[str] = set()
        unique_trades: list[ExchangeTrade] = []
        for t in trades:
            if t.trade_id not in seen:
                seen.add(t.trade_id)
                unique_trades.append(t)

        logger.info(f"Binance earn rewards found: {len(unique_trades)} (over {lookback_days}d)")
        return sorted(unique_trades, key=lambda x: x.timestamp, reverse=True)
