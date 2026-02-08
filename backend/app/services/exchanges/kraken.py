"""Kraken exchange service."""

import base64
import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlencode

import httpx

from app.services.exchanges.base import (
    BaseExchangeService,
    ExchangeBalance,
    ExchangeDeposit,
    ExchangeTrade,
    ExchangeWithdrawal,
)


class KrakenService(BaseExchangeService):
    """Kraken exchange integration."""

    BASE_URL = "https://api.kraken.com"

    # Kraken uses different asset names - known mappings
    ASSET_MAP = {
        "XXBT": "BTC",
        "XBT": "BTC",
        "XETH": "ETH",
        "XXRP": "XRP",
        "XXLM": "XLM",
        "XXMR": "XMR",
        "XLTC": "LTC",
        "XZEC": "ZEC",
        "XXDG": "DOGE",
        "XDOGE": "DOGE",
        "ZUSD": "USD",
        "ZEUR": "EUR",
        "ZGBP": "GBP",
        "ZJPY": "JPY",
        "ZCAD": "CAD",
        "XSOL": "SOL",
    }

    # Known quote currencies in Kraken pairs (order matters - longer first)
    QUOTE_CURRENCIES = ["ZEUR", "ZUSD", "ZGBP", "XXBT", "XETH", "EUR", "USD", "GBP", "BTC", "ETH", "USDT", "USDC"]

    # Fiat currencies (for filtering)
    FIAT_CURRENCIES = ["EUR", "USD", "GBP", "JPY", "CAD", "AUD", "CHF"]

    @property
    def exchange_name(self) -> str:
        return "Kraken"

    def _normalize_asset(self, asset: str) -> str:
        """Convert Kraken asset name to standard format.

        Kraken naming conventions:
        - XXBT, XETH, XLTC -> BTC, ETH, LTC (X prefix for crypto)
        - ZEUR, ZUSD, ZGBP -> EUR, USD, GBP (Z prefix for fiat)
        - PEPE.S, ETH2.S -> PEPE, ETH (.S suffix for staked assets)
        - Modern assets use standard names: SOL, DOT, ADA, etc.
        """
        # Remove staking/reward suffixes first
        # Kraken uses .S for staked, .M for margin, .F for flex staking
        for suffix in [".S", ".M", ".F", ".P", "2.S"]:
            if asset.endswith(suffix):
                asset = asset[:-len(suffix)]
                break

        # Check known mappings first
        if asset in self.ASSET_MAP:
            return self.ASSET_MAP[asset]

        # Handle X prefix for older crypto assets (XXBT -> XBT -> BTC already handled)
        # Some assets have double X like XXBT, some have single X like XETH
        if asset.startswith("XX") and len(asset) > 2:
            # Try removing XX prefix
            stripped = asset[2:]
            if stripped in self.ASSET_MAP:
                return self.ASSET_MAP[stripped]
            return stripped

        if asset.startswith("X") and len(asset) > 3:
            # Try removing X prefix (XETH -> ETH)
            stripped = asset[1:]
            if stripped in self.ASSET_MAP:
                return self.ASSET_MAP[stripped]
            # Only return stripped if it looks like a valid symbol (3-5 chars)
            if 3 <= len(stripped) <= 5:
                return stripped

        # Handle Z prefix for fiat (ZEUR -> EUR)
        if asset.startswith("Z") and len(asset) == 4:
            return asset[1:]

        # Return as-is for modern assets (SOL, DOT, ADA, PEPE, etc.)
        return asset

    def _extract_base_from_pair(self, pair: str) -> tuple[str, str]:
        """Extract and normalize base and quote assets from a Kraken trading pair.

        Kraken pairs have various formats:
        - XXBTZEUR -> (BTC, EUR)
        - XETHZEUR -> (ETH, EUR)
        - BTCEUR -> (BTC, EUR)
        - ETHEUR -> (ETH, EUR)
        - SOLEUR -> (SOL, EUR)
        - XXBTZUSD -> (BTC, USD)

        Returns:
            tuple: (base_asset, quote_currency) both normalized
        """
        # Try to find and remove quote currency
        for quote in self.QUOTE_CURRENCIES:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                normalized_base = self._normalize_asset(base)
                normalized_quote = self._normalize_asset(quote)
                return normalized_base, normalized_quote

        # Fallback: try to extract using common patterns
        # For pairs like XXBTZEUR where Z is a separator
        for quote in ["EUR", "USD", "GBP"]:
            zquote = f"Z{quote}"
            if pair.endswith(zquote):
                base = pair[:-len(zquote)]
                return self._normalize_asset(base), quote

        # Last resort: return first 3-4 chars normalized, assume EUR
        if pair.startswith("X") and len(pair) > 6:
            base = pair[:4]  # XXBT, XETH, etc.
        else:
            base = pair[:3]  # BTC, ETH, etc.

        return self._normalize_asset(base), "EUR"

    def _sign_request(self, uri_path: str, data: dict) -> dict:
        """Sign a request with Kraken's signature method."""
        nonce = str(int(time.time() * 1000))
        data["nonce"] = nonce

        post_data = urlencode(data)
        encoded = (nonce + post_data).encode()
        message = uri_path.encode() + hashlib.sha256(encoded).digest()

        signature = hmac.new(
            base64.b64decode(self.secret_key),
            message,
            hashlib.sha512,
        )

        return {
            "API-Key": self.api_key,
            "API-Sign": base64.b64encode(signature.digest()).decode(),
        }

    async def test_connection(self) -> bool:
        """Test if the API connection is working."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            async with httpx.AsyncClient() as client:
                uri_path = "/0/private/Balance"
                data = {}
                headers = self._sign_request(uri_path, data)

                response = await client.post(
                    f"{self.BASE_URL}{uri_path}",
                    data=data,
                    headers=headers,
                    timeout=10.0,
                )
                result = response.json()
                errors = result.get("error", [])
                if errors:
                    logger.error(f"Kraken API error: {errors}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Kraken connection test failed: {type(e).__name__}: {e}")
            return False

    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all non-zero balances from Kraken."""
        balances = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/Balance"
            data = {}
            headers = self._sign_request(uri_path, data)

            response = await client.post(
                f"{self.BASE_URL}{uri_path}",
                data=data,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("error"):
                raise Exception(str(result["error"]))

            for asset, balance_str in result.get("result", {}).items():
                balance = Decimal(balance_str)
                if balance > 0:
                    normalized_asset = self._normalize_asset(asset)
                    balances.append(
                        ExchangeBalance(
                            symbol=normalized_asset,
                            free=balance,
                            locked=Decimal("0"),
                            total=balance,
                        )
                    )

        return balances

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[ExchangeTrade]:
        """Get trade history from Kraken with pagination."""
        trades = []
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
                    break  # No more trades

                for trade_id, trade in trades_data.items():
                    if len(trades) >= limit:
                        break

                    pair = trade["pair"]
                    # Extract and normalize base and quote from pair
                    base_asset, quote_currency = self._extract_base_from_pair(pair)

                    # Create normalized symbol (e.g., BTCEUR instead of XXBTZEUR)
                    # This makes it compatible with the import logic
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
                            timestamp=datetime.fromtimestamp(trade["time"]),
                        )
                    )

                # Move to next page (Kraken returns 50 trades per page)
                offset += len(trades_data)

                # If we got less than 50 trades, we've reached the end
                if len(trades_data) < 50:
                    break

        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_deposits(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeDeposit]:
        """Get deposit history from Kraken."""
        deposits = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/DepositStatus"
            data = {}

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
                        timestamp=datetime.fromtimestamp(deposit["time"]),
                        status=deposit["status"],
                        tx_id=deposit.get("txid"),
                    )
                )

        return deposits

    async def get_withdrawals(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExchangeWithdrawal]:
        """Get withdrawal history from Kraken."""
        withdrawals = []

        async with httpx.AsyncClient() as client:
            uri_path = "/0/private/WithdrawStatus"
            data = {}

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
                        timestamp=datetime.fromtimestamp(withdrawal["time"]),
                        status=withdrawal["status"],
                        tx_id=withdrawal.get("txid"),
                    )
                )

        return withdrawals

    async def get_ledgers(
        self,
        asset: Optional[str] = None,
        ledger_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[dict]:
        """Get ledger entries from Kraken.

        Ledgers contain ALL transactions including Instant Buy purchases,
        trades, deposits, withdrawals, staking rewards, etc.

        Types: trade, deposit, withdrawal, receive, spend, staking, etc.
        """
        ledgers = []
        offset = 0

        async with httpx.AsyncClient() as client:
            while len(ledgers) < limit:
                uri_path = "/0/private/Ledgers"
                data = {"ofs": offset}

                if asset:
                    data["asset"] = asset
                if ledger_type:
                    data["type"] = ledger_type
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
                    print(f"Ledgers error: {result.get('error')}")
                    break

                ledgers_data = result.get("result", {}).get("ledger", {})

                if not ledgers_data:
                    break

                for ledger_id, entry in ledgers_data.items():
                    if len(ledgers) >= limit:
                        break

                    ledgers.append({
                        "ledger_id": ledger_id,
                        "refid": entry.get("refid", ""),
                        "time": datetime.fromtimestamp(entry["time"]),
                        "type": entry["type"],
                        "subtype": entry.get("subtype", ""),
                        "aclass": entry.get("aclass", ""),
                        "asset": self._normalize_asset(entry["asset"]),
                        "amount": Decimal(entry["amount"]),
                        "fee": Decimal(entry["fee"]),
                        "balance": Decimal(entry["balance"]),
                    })

                offset += len(ledgers_data)

                if len(ledgers_data) < 50:
                    break

        return sorted(ledgers, key=lambda x: x["time"], reverse=True)

    async def get_instant_buys(self, limit: int = 500) -> List[ExchangeTrade]:
        """Extract Instant Buy transactions from ledgers.

        Instant Buy shows as paired 'spend' (EUR) and 'receive' (crypto) entries
        with the same refid.
        """
        trades = []

        # Get all ledger entries
        ledgers = await self.get_ledgers(limit=limit * 2)

        # Group by refid to find paired transactions
        by_refid = {}
        for entry in ledgers:
            refid = entry["refid"]
            if refid:
                if refid not in by_refid:
                    by_refid[refid] = []
                by_refid[refid].append(entry)

        # Find spend/receive pairs (Instant Buy)
        processed_refids = set()
        for refid, entries in by_refid.items():
            if refid in processed_refids:
                continue

            # Look for spend (negative fiat) + receive (positive crypto) pairs
            spend_entry = None
            receive_entry = None

            for entry in entries:
                amount = entry["amount"]
                asset = entry["asset"]
                entry_type = entry["type"]

                # Spend is negative fiat (EUR, USD)
                if entry_type == "spend" or (amount < 0 and asset in ["EUR", "USD", "GBP"]):
                    spend_entry = entry
                # Receive is positive crypto
                elif entry_type == "receive" or (amount > 0 and asset not in ["EUR", "USD", "GBP"]):
                    receive_entry = entry

            # If we have both, it's an Instant Buy
            if spend_entry and receive_entry:
                crypto_amount = abs(receive_entry["amount"])
                fiat_amount = abs(spend_entry["amount"])

                if crypto_amount > 0:
                    price = fiat_amount / crypto_amount

                    trades.append(
                        ExchangeTrade(
                            trade_id=f"instant_{refid}",
                            symbol=f"{receive_entry['asset']}EUR",
                            side="buy",
                            quantity=crypto_amount,
                            price=price,
                            fee=spend_entry["fee"] + receive_entry["fee"],
                            fee_currency="EUR",
                            timestamp=receive_entry["time"],
                        )
                    )
                    processed_refids.add(refid)

        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_crypto_conversions(self, limit: int = 500) -> List[ExchangeTrade]:
        """Extract crypto-to-crypto conversions from ledgers.

        Conversions show as paired entries with the same refid:
        - One negative amount (crypto sold)
        - One positive amount (crypto received)
        Both assets are crypto (not fiat).
        """
        trades = []

        # Get all ledger entries
        ledgers = await self.get_ledgers(limit=limit * 2)

        # Group by refid to find paired transactions
        by_refid = {}
        for entry in ledgers:
            refid = entry["refid"]
            if refid:
                if refid not in by_refid:
                    by_refid[refid] = []
                by_refid[refid].append(entry)

        fiat_currencies = ["EUR", "USD", "GBP", "CAD", "JPY", "CHF", "AUD"]

        # Find crypto-to-crypto pairs
        processed_refids = set()
        for refid, entries in by_refid.items():
            if refid in processed_refids:
                continue

            # Look for pairs where both are crypto
            sell_entry = None
            buy_entry = None

            for entry in entries:
                amount = entry["amount"]
                asset = entry["asset"]

                # Skip if fiat currency
                if asset in fiat_currencies:
                    continue

                # Negative amount = sold crypto
                if amount < 0:
                    sell_entry = entry
                # Positive amount = received crypto
                elif amount > 0:
                    buy_entry = entry

            # If we have both crypto entries, it's a conversion
            if sell_entry and buy_entry:
                sell_amount = abs(sell_entry["amount"])
                buy_amount = abs(buy_entry["amount"])
                sell_asset = sell_entry["asset"]
                buy_asset = buy_entry["asset"]

                # Calculate implied price (how much of sell_asset per buy_asset)
                price = sell_amount / buy_amount if buy_amount > 0 else Decimal("0")

                # Create SELL trade for the source crypto
                trades.append(
                    ExchangeTrade(
                        trade_id=f"convert_sell_{refid}",
                        symbol=f"{sell_asset}{buy_asset}",
                        side="sell",
                        quantity=sell_amount,
                        price=price,
                        fee=sell_entry["fee"],
                        fee_currency=sell_asset,
                        timestamp=sell_entry["time"],
                    )
                )

                # Create BUY trade for the destination crypto
                trades.append(
                    ExchangeTrade(
                        trade_id=f"convert_buy_{refid}",
                        symbol=f"{buy_asset}{sell_asset}",
                        side="buy",
                        quantity=buy_amount,
                        price=Decimal("1") / price if price > 0 else Decimal("0"),
                        fee=buy_entry["fee"],
                        fee_currency=buy_asset,
                        timestamp=buy_entry["time"],
                    )
                )

                processed_refids.add(refid)
                print(f"Kraken: Found conversion {sell_asset} -> {buy_asset}")

        print(f"Kraken: Total crypto conversions found: {len(trades) // 2}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_rewards(self, limit: int = 500) -> List[ExchangeTrade]:
        """Extract staking rewards and other rewards from ledgers.

        Rewards appear as single entries with positive amounts.
        Types include: reward, staking, credit, airdrop, bonus, earn.
        """
        trades = []

        # Get all ledger entries
        ledgers = await self.get_ledgers(limit=limit)

        # Reward types from Kraken (including promotional rewards like Spin & Win)
        reward_types = ["reward", "staking", "credit", "airdrop", "bonus", "earn"]

        for entry in ledgers:
            entry_type = entry["type"]
            subtype = entry.get("subtype", "").lower()
            amount = entry["amount"]
            asset = entry["asset"]

            # Skip fiat currencies
            if asset in ["EUR", "USD", "GBP", "CAD", "JPY"]:
                continue

            # Process rewards and staking (including Spin & Win, promotions, etc.)
            is_reward = entry_type in reward_types or subtype in reward_types
            if is_reward and amount > 0:
                # Determine if it's staking or promotional reward (airdrop)
                is_staking = entry_type == "staking" or subtype == "staking"
                reward_prefix = "reward_staking_" if is_staking else "reward_airdrop_"

                trades.append(
                    ExchangeTrade(
                        trade_id=f"{reward_prefix}{entry['ledger_id']}",
                        symbol=f"{asset}EUR",
                        side="buy",  # Treat as buy with price 0
                        quantity=amount,
                        price=Decimal("0"),  # Rewards are "free"
                        fee=entry["fee"],
                        fee_currency="EUR",
                        timestamp=entry["time"],
                    )
                )
                print(f"  Kraken reward: {entry_type}/{subtype} - {amount} {asset}")

        return sorted(trades, key=lambda x: x.timestamp, reverse=True)
