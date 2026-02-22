"""Bitstamp exchange service."""

import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class BitstampService(BaseExchangeService):
    """Bitstamp exchange integration.

    Authentication uses HMAC SHA256 signatures with custom headers.
    API docs: https://www.bitstamp.net/api/
    """

    BASE_URL = "https://www.bitstamp.net"

    # Known currency suffixes in Bitstamp balance keys
    KNOWN_CURRENCIES = [
        "btc",
        "eth",
        "xrp",
        "ltc",
        "bch",
        "xlm",
        "link",
        "omg",
        "usdc",
        "pax",
        "gbp",
        "eur",
        "usd",
        "sol",
        "ada",
        "dot",
        "matic",
        "avax",
        "doge",
        "shib",
        "uni",
        "aave",
        "algo",
        "atom",
        "near",
        "ape",
        "sand",
        "mana",
        "axs",
        "grt",
        "mkr",
        "snx",
        "comp",
        "crv",
        "sushi",
        "yfi",
        "bat",
        "enj",
        "storj",
        "skl",
        "ftm",
        "imx",
        "op",
        "arb",
        "pepe",
        "floki",
        "sui",
        "apt",
        "rndr",
        "inj",
        "fet",
    ]

    @property
    def exchange_name(self) -> str:
        return "Bitstamp"

    def _generate_auth_headers(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
        content_type: str = "",
    ) -> dict:
        """Generate authentication headers for Bitstamp API v2.

        Signature payload format:
            BITSTAMP <api_key> + method + host + path + query + content_type + nonce + timestamp + v2 + body
        """
        nonce = str(uuid.uuid4())
        timestamp = str(int(time.time() * 1000))
        host = "www.bitstamp.net"

        x_auth = f"BITSTAMP {self.api_key}"

        # Build the message to sign
        message = x_auth + method.upper() + host + path + query + content_type + nonce + timestamp + "v2" + body

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-Auth": x_auth,
            "X-Auth-Signature": signature,
            "X-Auth-Nonce": nonce,
            "X-Auth-Timestamp": timestamp,
            "X-Auth-Version": "v2",
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/balance/"
                headers = self._generate_auth_headers("POST", path)

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=15.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Bitstamp test_connection error: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Bitstamp.

        The balance endpoint returns a flat dict with keys like:
            btc_balance, btc_available, btc_reserved,
            eth_balance, eth_available, eth_reserved, etc.
        """
        balances = []

        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/balance/"
                headers = self._generate_auth_headers("POST", path)

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                # Parse the flat balance dict into structured balances
                seen_currencies = set()

                for currency in self.KNOWN_CURRENCIES:
                    balance_key = f"{currency}_balance"
                    available_key = f"{currency}_available"
                    reserved_key = f"{currency}_reserved"

                    if balance_key in data:
                        total = Decimal(str(data.get(balance_key, "0")))
                        available = Decimal(str(data.get(available_key, "0")))
                        reserved = Decimal(str(data.get(reserved_key, "0")))

                        if total > 0:
                            symbol = currency.upper()
                            seen_currencies.add(symbol)
                            balances.append(
                                ExchangeBalance(
                                    symbol=symbol,
                                    free=available,
                                    locked=reserved,
                                    total=total,
                                )
                            )

                # Also scan for any unknown currencies in the response
                for key in data:
                    if key.endswith("_balance"):
                        currency = key.replace("_balance", "").upper()
                        if currency not in seen_currencies:
                            total = Decimal(str(data.get(key, "0")))
                            if total > 0:
                                available = Decimal(str(data.get(f"{currency.lower()}_available", "0")))
                                reserved = Decimal(str(data.get(f"{currency.lower()}_reserved", "0")))
                                balances.append(
                                    ExchangeBalance(
                                        symbol=currency,
                                        free=available,
                                        locked=reserved,
                                        total=total,
                                    )
                                )

        except Exception as e:
            logger.error(f"Bitstamp get_balances error: {e}")

        return balances

    async def _get_user_transactions(
        self,
        offset: int = 0,
        limit: int = 100,
        sort: str = "desc",
    ) -> list:
        """Fetch user transactions from Bitstamp.

        Transaction types:
            0 = deposit
            1 = withdrawal
            2 = trade
            14 = sub account transfer
        """
        try:
            async with httpx.AsyncClient() as client:
                path = "/api/v2/user_transactions/"
                body = f"offset={offset}&limit={limit}&sort={sort}"
                content_type = "application/x-www-form-urlencoded"

                headers = self._generate_auth_headers("POST", path, body=body, content_type=content_type)
                headers["Content-Type"] = content_type

                response = await client.post(
                    f"{self.BASE_URL}{path}",
                    content=body,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Bitstamp user_transactions error: {response.status_code} - {response.text[:200]}")
                    return []

                return response.json()

        except Exception as e:
            logger.error(f"Bitstamp _get_user_transactions error: {e}")
            return []

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Bitstamp.

        Trades are extracted from user_transactions where type=2.
        """
        trades = []
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

                    # Only process trades (type=2)
                    if int(tx.get("type", -1)) != 2:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    # Apply time filters
                    if start_time and tx_datetime < start_time:
                        continue
                    if end_time and tx_datetime > end_time:
                        continue

                    # Determine which currency pair was traded
                    # Bitstamp returns amounts as keys like "btc", "eth", "usd", "eur"
                    # A trade has one positive and one negative amount
                    trade_data = self._parse_trade_from_transaction(tx, tx_datetime)
                    if trade_data:
                        trades.append(trade_data)

                # Paginate
                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:
            logger.error(f"Bitstamp get_trades error: {e}")

        logger.info(f"Bitstamp: Total trades found: {len(trades)}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    def _parse_trade_from_transaction(self, tx: dict, tx_datetime: datetime) -> Optional[ExchangeTrade]:
        """Parse a trade from a Bitstamp user transaction.

        In a trade transaction, one currency amount is positive (bought)
        and another is negative (sold).
        """
        fiat_currencies = {"usd", "eur", "gbp"}
        bought_currency = None
        bought_amount = Decimal("0")
        sold_currency = None
        sold_amount = Decimal("0")

        for key, value in tx.items():
            # Skip non-currency keys
            if key in ("id", "type", "datetime", "fee", "order_id"):
                continue

            try:
                amount = Decimal(str(value))
            except Exception:
                continue

            if amount > 0 and key.lower() not in ("id", "type", "fee"):
                bought_currency = key.upper()
                bought_amount = amount
            elif amount < 0:
                sold_currency = key.upper()
                sold_amount = abs(amount)

        if not bought_currency or not sold_currency:
            return None

        # Determine side: if the bought asset is fiat, it's a sell; otherwise it's a buy
        if bought_currency.lower() in fiat_currencies:
            # Sold crypto for fiat
            side = "sell"
            symbol = f"{sold_currency}_{bought_currency}"
            quantity = sold_amount
            price = bought_amount / sold_amount if sold_amount > 0 else Decimal("0")
        else:
            # Bought crypto with fiat or another crypto
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

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Bitstamp.

        Deposits are extracted from user_transactions where type=0.
        """
        deposits = []
        offset = 0
        page_size = 100

        try:
            while len(deposits) < limit:
                transactions = await self._get_user_transactions(offset=offset, limit=page_size)

                if not transactions:
                    break

                for tx in transactions:
                    if len(deposits) >= limit:
                        break

                    # Only process deposits (type=0)
                    if int(tx.get("type", -1)) != 0:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    if start_time and tx_datetime < start_time:
                        continue

                    # Find which currency was deposited (positive amount)
                    deposit_currency = None
                    deposit_amount = Decimal("0")

                    for key, value in tx.items():
                        if key in ("id", "type", "datetime", "fee", "order_id"):
                            continue
                        try:
                            amount = Decimal(str(value))
                            if amount > 0:
                                deposit_currency = key.upper()
                                deposit_amount = amount
                                break
                        except Exception:
                            continue

                    if not deposit_currency:
                        continue

                    if symbol and deposit_currency != symbol.upper():
                        continue

                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=str(tx.get("id", "")),
                            symbol=deposit_currency,
                            amount=deposit_amount,
                            timestamp=tx_datetime,
                            status="completed",
                            tx_id=None,
                        )
                    )

                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:
            logger.error(f"Bitstamp get_deposits error: {e}")

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Bitstamp.

        Withdrawals are extracted from user_transactions where type=1.
        """
        withdrawals = []
        offset = 0
        page_size = 100

        try:
            while len(withdrawals) < limit:
                transactions = await self._get_user_transactions(offset=offset, limit=page_size)

                if not transactions:
                    break

                for tx in transactions:
                    if len(withdrawals) >= limit:
                        break

                    # Only process withdrawals (type=1)
                    if int(tx.get("type", -1)) != 1:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    if start_time and tx_datetime < start_time:
                        continue

                    # Find which currency was withdrawn (negative amount)
                    withdrawal_currency = None
                    withdrawal_amount = Decimal("0")

                    for key, value in tx.items():
                        if key in ("id", "type", "datetime", "fee", "order_id"):
                            continue
                        try:
                            amount = Decimal(str(value))
                            if amount < 0:
                                withdrawal_currency = key.upper()
                                withdrawal_amount = abs(amount)
                                break
                        except Exception:
                            continue

                    if not withdrawal_currency:
                        continue

                    if symbol and withdrawal_currency != symbol.upper():
                        continue

                    fee = Decimal(str(tx.get("fee", "0")))

                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=str(tx.get("id", "")),
                            symbol=withdrawal_currency,
                            amount=withdrawal_amount,
                            fee=fee,
                            timestamp=tx_datetime,
                            status="completed",
                            tx_id=None,
                            address=None,
                        )
                    )

                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:
            logger.error(f"Bitstamp get_withdrawals error: {e}")

        return withdrawals
