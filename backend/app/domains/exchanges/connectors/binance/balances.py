import logging
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeBalance
from app.domains.exchanges.connectors.binance.core import BinanceCore

logger = logging.getLogger(__name__)


class BinanceBalances(BinanceCore):
    async def get_balances(self) -> list[ExchangeBalance]:  # noqa: C901
        balances: list[ExchangeBalance] = []

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
                free = Decimal(asset["free"])
                locked = Decimal(asset["locked"])
                total = free + locked

                self._all_account_symbols.add(asset["asset"])

                if total > 0:
                    balances.append(
                        ExchangeBalance(
                            symbol=asset["asset"],
                            free=free,
                            locked=locked,
                            total=total,
                        )
                    )

        try:
            earn_balances = await self._get_earn_positions()
            if earn_balances:
                balance_map = {b.symbol: b for b in balances}
                for symbol, total_amount in earn_balances.items():
                    ld_symbol = f"LD{symbol}"
                    if ld_symbol in balance_map:
                        old_total = balance_map[ld_symbol].total
                        if total_amount > old_total:
                            logger.info(
                                f"Earn position {symbol}: updating {ld_symbol} "
                                f"{float(old_total):.8f} → {float(total_amount):.8f} (incl. interest)"
                            )
                            balance_map[ld_symbol] = ExchangeBalance(
                                symbol=ld_symbol,
                                free=Decimal("0"),
                                locked=total_amount,
                                total=total_amount,
                            )
                    elif symbol not in balance_map:
                        balance_map[ld_symbol] = ExchangeBalance(
                            symbol=ld_symbol,
                            free=Decimal("0"),
                            locked=total_amount,
                            total=total_amount,
                        )
                balances = list(balance_map.values())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to fetch/apply earn positions, using spot balances only: {e}")

        try:
            funding_balances = await self._get_funding_positions()
            if funding_balances:
                balance_map = {b.symbol: b for b in balances}
                for symbol, amount in funding_balances.items():
                    if amount <= 0:
                        continue
                    self._all_account_symbols.add(symbol)
                    if symbol in balance_map:
                        existing = balance_map[symbol]
                        new_total = existing.total + amount
                        logger.info(
                            f"Funding wallet {symbol}: adding {float(amount):.8f} "
                            f"to spot {float(existing.total):.8f} → {float(new_total):.8f}"
                        )
                        balance_map[symbol] = ExchangeBalance(
                            symbol=symbol,
                            free=existing.free + amount,
                            locked=existing.locked,
                            total=new_total,
                        )
                    else:
                        logger.info(f"Funding wallet {symbol}: {float(amount):.8f} (not in spot)")
                        balance_map[symbol] = ExchangeBalance(
                            symbol=symbol,
                            free=amount,
                            locked=Decimal("0"),
                            total=amount,
                        )
                balances = list(balance_map.values())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to fetch/apply funding positions, using spot/earn balances only: {e}")

        return balances

    async def _get_earn_positions(self) -> dict[str, Decimal]:
        earn_totals: dict[str, Decimal] = {}

        async with self._get_http_client(timeout=30.0) as client:
            for endpoint in [
                "/sapi/v1/simple-earn/flexible/position",
                "/sapi/v1/simple-earn/locked/position",
            ]:
                try:
                    current = 1
                    while True:
                        params = self._sign_request({"current": current, "size": 100})
                        response = await self._api_get(
                            client,
                            f"{self.BASE_URL}{endpoint}",
                            params=params,
                            headers=self._get_headers(),
                        )
                        if response.status_code != 200:
                            logger.warning(f"Earn positions {endpoint}: HTTP {response.status_code}")
                            break
                        data = response.json()
                        rows = data.get("rows", [])
                        if not rows:
                            break
                        for row in rows:
                            asset = row.get("asset", "")
                            total_amount = Decimal(str(row.get("totalAmount", "0")))
                            if total_amount > 0 and asset:
                                earn_totals[asset] = earn_totals.get(asset, Decimal("0")) + total_amount
                                logger.debug(f"Earn {endpoint}: {asset} totalAmount={total_amount}")
                        total_pages = data.get("total", 0)
                        if current * 100 >= total_pages:
                            break
                        current += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Failed to fetch {endpoint}: {e}")

        if earn_totals:
            logger.info(f"Earn positions found: {dict((k, float(v)) for k, v in earn_totals.items())}")
        return earn_totals

    async def _get_funding_positions(self) -> dict[str, Decimal]:
        funding_totals: dict[str, Decimal] = {}

        async with self._get_http_client(timeout=30.0) as client:
            try:
                params = self._sign_request({})
                response = await self._api_post(
                    client,
                    f"{self.BASE_URL}/sapi/v1/asset/get-funding-asset",
                    params=params,
                    headers=self._get_headers(),
                )
                if response.status_code != 200:
                    logger.warning(f"Funding wallet: HTTP {response.status_code} — {response.text}")
                    return funding_totals
                data = response.json()
                for row in data or []:
                    asset = row.get("asset", "")
                    if not asset:
                        continue
                    total = (
                        Decimal(str(row.get("free", "0")))
                        + Decimal(str(row.get("locked", "0")))
                        + Decimal(str(row.get("freeze", "0")))
                        + Decimal(str(row.get("withdrawing", "0")))
                    )
                    if total > 0:
                        funding_totals[asset] = funding_totals.get(asset, Decimal("0")) + total
                        logger.debug(f"Funding wallet: {asset} total={total}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to fetch funding wallet: {e}")

        if funding_totals:
            logger.info(f"Funding wallet positions found: {dict((k, float(v)) for k, v in funding_totals.items())}")
        return funding_totals
